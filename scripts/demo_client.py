"""Shared SSE client; operator HTTP also uses the project's HTTP boundary."""

import asyncio
import json
from collections import Counter
from pathlib import Path
from time import monotonic
from uuid import UUID

import httpx

from api.app.providers.http import get_client

ROOT = Path(__file__).resolve().parents[1]
PAPERS = ("paper1_attention", "paper2_retracted_reference", "paper3_planted_problems")


async def sse_events(response):
    fields, data = {}, []
    async for line in response.aiter_lines():
        if not line:
            if data:
                yield {**fields, "payload": json.loads("\n".join(data))}
            fields, data = {}, []
        elif not line.startswith(":"):
            name, _, value = line.partition(":")
            value = value.removeprefix(" ")
            if name == "data":
                data.append(value)
            elif name in ("event", "id"):
                fields[name] = value


def verdict_counts(report):
    return {
        "existence": dict(Counter(row["status"] for row in report.get("existence", []))),
        "retractions": dict(Counter(row["status"] for row in report.get("retractions", []))),
        "support": dict(Counter(row["label"] for row in report.get("support", []))),
        "hidden_text": dict(Counter(row["kind"] for row in report.get("hidden_text", []))),
    }


async def run_job(base_url, paper, *, fresh=False, deadline=600, client=None):
    started = monotonic()
    result = {
        "paper": Path(paper).stem,
        "job_id": None,
        "report_url": None,
        "duration_seconds": 0,
        "stages": {},
        "counts": {},
        "failure": None,
    }
    client = client or get_client("demo-tools")
    base_url = base_url.rstrip("/")
    try:
        async with asyncio.timeout(deadline):
            body = await asyncio.to_thread(Path(paper).read_bytes)
            response = await client.post(
                base_url + "/jobs",
                params={"fresh": "1"} if fresh else {},
                files={"file": (Path(paper).name, body, "application/pdf")},
                timeout=30,
            )
            if response.status_code != 202:
                result["failure"] = f"POST /jobs returned HTTP {response.status_code}"
                return result
            job_id = str(UUID(response.json()["job_id"]))
            result.update(job_id=job_id, report_url=f"{base_url}/jobs/{job_id}")
            cursor, starts = 0, {}
            for _ in range(3):
                try:
                    async with client.stream(
                        "GET",
                        f"{base_url}/jobs/{job_id}/events",
                        headers={"Last-Event-ID": str(cursor)},
                        timeout=30,
                    ) as stream:
                        if stream.status_code != 200:
                            result["failure"] = f"SSE returned HTTP {stream.status_code}"
                            return result
                        async for event in sse_events(stream):
                            seq = int(event["id"])
                            if seq <= cursor:
                                continue
                            cursor = seq
                            payload = event["payload"]
                            if event["event"] == "stage":
                                name = payload["stage"]
                                if payload["status"] == "STARTED":
                                    starts[name] = monotonic()
                                elif name in starts:
                                    result["stages"][name] = round(
                                        monotonic() - starts.pop(name), 4
                                    )
                            if event["event"] == "done":
                                result.update(
                                    counts=verdict_counts(payload),
                                    status=payload["status"],
                                    demo_fixture=payload.get("demo_fixture", False),
                                )
                                if payload["status"] == "CHECK_INCOMPLETE":
                                    result["failure"] = payload.get("reason") or "CHECK_INCOMPLETE"
                                return result
                except httpx.TransportError:
                    pass  # Resume from the last durable event ID on the next connection.
                await asyncio.sleep(0.2)
            result["failure"] = "SSE ended without a done event after three connections"
    except Exception as error:
        # Exceptions may contain URLs/credentials or external payloads: print only the type.
        result["failure"] = f"Demo request incomplete ({type(error).__name__})"
    finally:
        result["duration_seconds"] = round(monotonic() - started, 4)
    return result
