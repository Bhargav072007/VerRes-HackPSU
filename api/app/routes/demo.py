import asyncio
import hashlib
import json
from asyncio import sleep
from contextlib import suppress
from pathlib import Path

from fastapi.sse import format_sse_event
from starlette.concurrency import run_in_threadpool

from api.app.db import EVENTS, JobFailure

DEMO_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "events" / "job.json"
DEMO_DELAY = 0.5
RECORDINGS = Path(__file__).resolve().parents[3] / "fixtures" / "demo"
DEMO_PAPERS = ("paper1_attention", "paper2_retracted_reference", "paper3_planted_problems")


def recording_name(job_input):
    if isinstance(job_input, str):
        job_input = json.loads(job_input)
    pdfs = RECORDINGS.parent / "pdfs"
    for index, name in enumerate(DEMO_PAPERS, 1):
        path = pdfs / f"{name}.pdf"
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == job_input.get(
            "sha256"
        ):
            return f"paper{index}"
    return None


def load_recording(job_input):
    """Missing or invalid recordings never fall back to invented/live results."""
    try:
        name = recording_name(job_input)
        if not name:
            return "Demo recording missing: input is not one of the three demo PDFs."
        path = RECORDINGS / f"{name}.jsonl"
        if not path.is_file():
            return f"Demo recording missing: fixtures/demo/{name}.jsonl; record a real run first."
        raw = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        events = validate_recording(raw)
        if isinstance(events, str):
            return events
        expected = json.loads(job_input) if isinstance(job_input, str) else job_input
        if any(item.get("input_sha256") != expected.get("sha256") for item in raw):
            return "Demo recording invalid: PDF digest does not match."
        return events
    except (OSError, ValueError, TypeError, KeyError):
        return "Demo recording invalid: could not read a complete recording."


def validate_recording(raw):
    try:
        events = [
            EVENTS.validate_python({k: item[k] for k in ("job_id", "seq", "type", "payload")})
            for item in raw
        ]
        if (
            not events
            or events[-1].type != "done"
            or any(event.type == "done" for event in events[:-1])
            or [event.seq for event in events] != list(range(1, len(events) + 1))
            or any(event.job_id != events[0].job_id for event in events)
            or events[-1].payload.job_id != events[0].job_id
            or any(item.get("demo_fixture") or item["payload"].get("demo_fixture") for item in raw)
        ):
            return "Demo recording invalid: expected a complete, ordered real-job journal."
        return events
    except (ValueError, TypeError, KeyError):
        return "Demo recording invalid: event contract validation failed."


async def replay_recording(bus, job_id, job_input):
    recorded = await run_in_threadpool(load_recording, job_input)
    if isinstance(recorded, str):
        await bus.emit(
            job_id,
            "done",
            {"job_id": str(job_id), "status": "CHECK_INCOMPLETE", "reason": recorded},
        )
        return
    for event in recorded:
        payload = event.payload.model_dump(mode="json")
        if event.type == "done":
            payload["job_id"] = str(job_id)
        result = await bus.emit(job_id, event.type, payload)
        if isinstance(result, JobFailure):
            return
        await asyncio.sleep(2 / len(recorded))


async def fixture_journal(job_id, job_input):
    recorded = await run_in_threadpool(load_recording, job_input)
    if isinstance(recorded, str):
        recorded = [
            EVENTS.validate_python(
                {
                    "job_id": job_id,
                    "seq": 1,
                    "type": "done",
                    "payload": {
                        "job_id": str(job_id),
                        "status": "CHECK_INCOMPLETE",
                        "reason": recorded,
                    },
                }
            )
        ]
    journal = []
    for event in recorded:
        item = event.model_dump(mode="json")
        item["job_id"] = str(job_id)
        if item["type"] == "done":
            item["payload"]["job_id"] = str(job_id)
        journal.append(item)
    return journal


async def fixture_stream(journal, cursor):
    for event in journal:
        if event["seq"] > cursor:
            await asyncio.sleep(2 / len(journal))
            yield format_sse_event(
                id=str(event["seq"]),
                event=event["type"],
                data_str=json.dumps({**event["payload"], "demo_fixture": True}),
            )


def mark_fixture(snapshot):
    snapshot["demo_fixture"] = True
    for event in snapshot.get("events", []):
        event["payload"]["demo_fixture"] = True
    return snapshot


async def run_fake_job(bus, job_id):
    """Development fixture stub; it never invokes a model or a network provider."""
    completed = False
    try:
        fixtures = json.loads(DEMO_FIXTURE.read_text())
        for event in fixtures:
            kind, payload = event["type"], event["payload"]
            if kind == "error":
                continue
            if kind == "done":
                payload["job_id"] = str(job_id)
                payload["review"]["warning"] = (
                    "Development fixture data; no external checks performed."
                )
            if kind == "review_summary":
                payload["warning"] = "Development fixture data; no external checks performed."
            await sleep(DEMO_DELAY)
            result = await bus.emit(job_id, kind, payload)
            if isinstance(result, JobFailure):
                break
            completed = kind == "done"
            if kind not in ("stage", "done"):
                await sleep(DEMO_DELAY)
                result = await bus.emit(job_id, "stage", {"stage": kind, "status": "COMPLETED"})
                if isinstance(result, JobFailure):
                    break
    except (Exception, asyncio.CancelledError):
        # Avoid leaking exception text, including credentials, from detached tasks.
        pass
    finally:
        if not completed:
            with suppress(Exception):
                await bus.emit(
                    job_id,
                    "done",
                    {
                        "job_id": str(job_id),
                        "status": "CHECK_INCOMPLETE",
                        "reason": "Development fixture stream could not be completed.",
                    },
                )
