import asyncio
import json
from asyncio import sleep
from contextlib import suppress
from pathlib import Path

from api.app.db import JobFailure

DEMO_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "events" / "job.json"
DEMO_DELAY = 0.5


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
