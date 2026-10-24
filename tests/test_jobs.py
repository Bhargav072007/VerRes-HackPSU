import asyncio
import hashlib
import json
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from pydantic import ValidationError

from api.app import main, sse
from api.app.db import EVENTS, JobFailure, Jobs
from api.app.routes import demo, jobs
from api.app.settings import Settings
from api.app.sse import EventBus
from tests.conftest import FIXTURES


@pytest.fixture
def job_app(monkeypatch, tmp_path, job_pool):
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    # A2 tests exercise intake/journal independently; A3 tests run the real runner.
    monkeypatch.setattr(main.Runner, "start", Mock())
    return main.create_app(
        Settings(
            _env_file=None, env="dev", data_dir=tmp_path, frontend_origin="https://frontend.example"
        )
    )


@pytest.fixture
async def job_client(job_app):
    async with job_app.router.lifespan_context(job_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=job_app), base_url="http://test"
        ) as client:
            yield client


@pytest.fixture
def intake():
    return json.loads((FIXTURES / "providers" / "intake.json").read_text())


def frames(content):
    return [
        dict(line.split(": ", 1) for line in block.splitlines())
        for block in content.decode().split("\n\n")
        if block and not block.startswith(":")
    ]


@pytest.mark.parametrize("case", ["arxiv", "doi"])
async def test_json_intake(job_client, job_pool, intake, case):
    response = await job_client.post("/jobs", json=intake[case])
    assert response.status_code == 202
    assert set(response.json()) == {"job_id"}
    row = job_pool.rows[UUID(response.json()["job_id"])]
    assert row["status"] == "QUEUED"
    assert row["input"] == intake[case]


@pytest.mark.parametrize(
    "case", ["neither", "both", "both_null", "blank", "null", "wrong_type", "extra"]
)
async def test_json_intake_invalid(job_client, job_pool, intake, case):
    response = await job_client.post("/jobs", json=intake[case])
    assert response.status_code == 400
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "invalid_request"
    assert not job_pool.rows


@pytest.mark.parametrize(
    "body,media",
    [
        (b"{", "application/json"),
        (b"x" * 4097, "application/json"),
        (b"pdf", "application/pdf"),
        (b"broken", "multipart/form-data"),
    ],
)
async def test_malformed_request_envelope(job_client, body, media):
    response = await job_client.post("/jobs", content=body, headers={"Content-Type": media})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
    assert set(response.json()) == {"code", "message"}


@pytest.mark.parametrize("pages", [1, 80])
async def test_pdf_file_field_accepted(job_client, job_pool, job_app, pages):
    data = (FIXTURES / "pdfs" / f"{pages}_pages.pdf").read_bytes()
    response = await job_client.post(
        "/jobs", files={"file": ("paper.pdf", data, "application/pdf")}
    )
    assert response.status_code == 202
    digest = hashlib.sha256(data).hexdigest()
    row = job_pool.rows[UUID(response.json()["job_id"])]
    assert row["status"] == "QUEUED" and row["input"] == {"sha256": digest}
    uploads = job_app.state.settings.data_dir / "uploads"
    assert (uploads / f"{digest}.pdf").read_bytes() == data
    assert len(list(uploads.iterdir())) == 1


@pytest.mark.parametrize(
    "data,code",
    [
        (b"text", "pdf_invalid"),
        (b"%PDF-broken", "pdf_invalid"),
        (b"%PDF-" + b"x" * jobs.PDF_LIMIT, "pdf_too_large"),
        ((FIXTURES / "pdfs" / "81_pages.pdf").read_bytes(), "too_many_pages"),
        ((FIXTURES / "pdfs" / "0_pages.pdf").read_bytes(), "pdf_invalid"),
    ],
)
async def test_pdf_rejected(job_client, job_pool, data, code):
    response = await job_client.post("/jobs", files={"file": ("paper.pdf", data)})
    assert response.status_code == (413 if code == "pdf_too_large" else 400)
    assert response.json()["code"] == code
    assert set(response.json()) == {"code", "message"}
    assert not job_pool.rows


async def test_multipart_requires_file(job_client, job_pool):
    response = await job_client.post("/jobs", files={"pdf": ("paper.pdf", b"%PDF-")})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
    assert not job_pool.rows


async def test_hourly_limit_and_expiry(job_client, job_pool, intake):
    for _ in range(5):
        assert (await job_client.post("/jobs", json=intake["doi"])).status_code == 202
    response = await job_client.post("/jobs", json=intake["doi"])
    assert response.status_code == 429 and response.json()["code"] == "rate_limited"
    for row in job_pool.rows.values():
        row["created_at"] -= timedelta(hours=2)
    assert (await job_client.post("/jobs", json=intake["arxiv"])).status_code == 202


async def test_global_running_limit(job_client, job_pool, job_app, intake):
    store = job_app.state.event_bus.jobs
    for index in range(3):
        assert isinstance(await store.create(f"192.0.2.{index}", {}, running=True), UUID)
    response = await job_client.post("/jobs", json=intake["doi"])
    assert response.status_code == 429 and response.json()["code"] == "rate_limited"
    response = await job_client.post("/dev/fake-job")
    assert response.status_code == 429 and response.json()["code"] == "rate_limited"
    assert len(job_pool.rows) == 3


async def test_concurrent_admission_and_starts(job_pool, events):
    bus = EventBus(Jobs(job_pool))
    admitted = await asyncio.gather(*(bus.jobs.create("same-ip", {}) for _ in range(6)))
    assert sum(isinstance(result, UUID) for result in admitted) == 5
    started = await asyncio.gather(
        *(
            bus.emit(job_id, "stage", events[0]["payload"])
            for job_id in admitted
            if isinstance(job_id, UUID)
        )
    )
    assert sum(not isinstance(result, JobFailure) for result in started) == 3
    assert sum(row["status"] == "RUNNING" for row in job_pool.rows.values()) == 3
    assert sum("pg_advisory_xact_lock" in sql for sql in job_pool.sql) == 11


async def test_snapshot_every_event(job_client, job_app, events, intake):
    response = await job_client.post("/jobs", json=intake["doi"])
    job_id = UUID(response.json()["job_id"])
    path = f"/jobs/{job_id}"
    initial = (await job_client.get(path)).json()
    assert initial["job"]["input"] == intake["doi"]
    for field in (
        "existence",
        "retractions",
        "sources",
        "support",
        "hidden_text",
        "review_comments",
        "stages",
        "errors",
        "events",
    ):
        assert initial[field] == []
    assert initial["paper"] is initial["review"] is initial["claim_map"] is None
    bus = job_app.state.event_bus
    for event in [*events[:10], events[-1]]:
        await bus.emit(job_id, event["type"], event["payload"])
    state = (await job_client.get(path)).json()
    assert state["status"] == state["job"]["status"] == "RUNNING"
    assert state["paper"]["id"] == "paper-1"
    assert all(
        len(state[key]) == 1
        for key in (
            "existence",
            "retractions",
            "sources",
            "support",
            "hidden_text",
            "review_comments",
            "stages",
            "errors",
        )
    )
    assert state["claim_map"]["nodes"] and state["review"]["comments"]
    assert len(state["events"]) == 11
    done = {"job_id": str(job_id), "status": "COMPLETE"}
    await bus.emit(job_id, "done", done)
    state = (await job_client.get(path)).json()
    assert state["status"] == state["job"]["status"] == "COMPLETE"
    assert state["support"][0]["evidence"][0]["quote"] in state["sources"][0]["passages"][0]["text"]


async def test_sse_http_replay_from_five(job_client, job_app, events):
    bus = job_app.state.event_bus
    job_id = await bus.jobs.create("replay-ip", {})
    for event in events[:10]:
        await bus.emit(job_id, event["type"], event["payload"])
    await bus.emit(job_id, "done", {**events[-2]["payload"], "job_id": str(job_id)})
    response = await job_client.get(f"/jobs/{job_id}/events", headers={"Last-Event-ID": "5"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    received = frames(response.content)
    assert [int(frame["id"]) for frame in received] == list(range(6, 12))
    assert received[-1]["event"] == "done"
    for frame in received:
        EVENTS.validate_python(
            {
                "job_id": job_id,
                "seq": int(frame["id"]),
                "type": frame["event"],
                "payload": json.loads(frame["data"]),
            }
        )
    assert not bus.subscribers
    response = await job_client.get(f"/jobs/{job_id}/events", headers={"Last-Event-ID": "11"})
    assert response.content == b""


async def test_replay_live_race(job_pool, events, monkeypatch):
    bus = EventBus(Jobs(job_pool))
    job_id = await bus.jobs.create("race-ip", {})
    for _ in range(6):
        await bus.emit(job_id, "stage", events[0]["payload"])
    original = bus.jobs.read_events
    replaying = asyncio.Event()
    resume = asyncio.Event()

    async def paused_replay(job_id, cursor):
        batch = await original(job_id, cursor)
        if not replaying.is_set():
            replaying.set()
            await resume.wait()
        return batch

    monkeypatch.setattr(bus.jobs, "read_events", paused_replay)
    stream = bus.stream(job_id, 5)
    first = asyncio.create_task(anext(stream))
    await asyncio.wait_for(replaying.wait(), 1)
    assert len(bus.subscribers[job_id]) == 1
    await asyncio.gather(*(bus.emit(job_id, "stage", events[0]["payload"]) for _ in range(10)))
    await bus.emit(job_id, "done", {"job_id": str(job_id), "status": "COMPLETE"})
    resume.set()
    received = [await first, *[frame async for frame in stream]]
    assert [int(frame["id"]) for frame in frames(b"".join(received))] == list(range(6, 18))
    assert not bus.subscribers


async def test_heartbeat_and_cross_worker_recovery(job_pool, monkeypatch):
    monkeypatch.setattr(sse, "HEARTBEAT_SECONDS", 0.01)
    bus = EventBus(Jobs(job_pool))
    other_worker = EventBus(bus.jobs)
    job_id = await bus.jobs.create("heartbeat-ip", {})
    stream = bus.stream(job_id)
    assert await asyncio.wait_for(anext(stream), 1) == b": ping\n\n"
    await other_worker.emit(job_id, "done", {"job_id": str(job_id), "status": "COMPLETE"})
    received = b"".join([frame async for frame in stream])
    assert frames(received)[0]["event"] == "done"
    assert not bus.subscribers


async def test_disconnect_cleans_queue(job_app, job_client, events):
    bus = job_app.state.event_bus
    job_id = await bus.jobs.create("disconnect-ip", {})
    await bus.emit(job_id, "stage", events[0]["payload"])
    delivered = asyncio.Event()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "query_string": b"",
        "path": f"/jobs/{job_id}/events",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }

    async def receive():
        await delivered.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            assert len(bus.subscribers[job_id]) == 1
            delivered.set()

    await asyncio.wait_for(job_app(scope, receive, send), 1)
    assert delivered.is_set() and not bus.subscribers


async def test_fake_job_contracts(job_client, job_app, job_pool, monkeypatch):
    sleeper = AsyncMock()
    monkeypatch.setattr(demo, "sleep", sleeper)
    response = await job_client.post("/dev/fake-job")
    assert response.status_code == 202
    await asyncio.gather(*list(job_app.state.tasks))
    job_id = UUID(response.json()["job_id"])
    response = await job_client.get(f"/jobs/{job_id}/events")
    received = frames(response.content)
    assert len(received) == 20
    assert sleeper.await_count == 20
    assert sum(call.args[0] for call in sleeper.await_args_list) == 10
    assert [int(frame["id"]) for frame in received] == list(range(1, 21))
    assert received[-1]["event"] == "done"
    assert {frame["event"] for frame in received} >= {
        "stage",
        "paper",
        "existence",
        "retraction",
        "source",
        "support",
        "review_summary",
        "done",
    }
    for frame in received:
        EVENTS.validate_python(
            {
                "job_id": job_id,
                "seq": int(frame["id"]),
                "type": frame["event"],
                "payload": json.loads(frame["data"]),
            }
        )
    assert job_pool.rows[job_id]["status"] == "COMPLETE"


@pytest.mark.parametrize("env", ["development", "test", "production"])
async def test_fake_job_absent_outside_dev(env):
    app = main.create_app(Settings(_env_file=None, env=env))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/dev/fake-job")
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message"}
    assert "/dev/fake-job" not in app.openapi()["paths"]


@pytest.mark.parametrize("suffix", ["", "/events"])
async def test_job_not_found(job_client, suffix):
    response = await job_client.get(f"/jobs/{uuid4()}{suffix}")
    assert response.status_code == 404 and response.json()["code"] == "job_not_found"


@pytest.mark.parametrize("cursor", ["-1", "abc", "1.2", "9223372036854775808", "１２"])
async def test_invalid_cursor(job_client, job_app, cursor):
    job_id = await job_app.state.event_bus.jobs.create("cursor-ip", {})
    # HTTP headers are bytes; use utf-8 here to exercise a non-ASCII value.
    response = await job_client.get(
        f"/jobs/{job_id}/events", headers={b"last-event-id": cursor.encode()}
    )
    assert response.status_code == 400 and response.json()["code"] == "invalid_request"


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("http://localhost:3000", True),
        ("https://frontend.example", True),
        ("https://evil.example", False),
    ],
)
async def test_cors(job_client, origin, allowed):
    response = await job_client.options(
        "/jobs",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)


async def test_failed_emit_rolls_back_and_does_not_notify(job_pool, events):
    bus = EventBus(Jobs(job_pool))
    job_id = await bus.jobs.create("rollback-ip", {})
    queue = asyncio.Queue()
    bus.subscribers[job_id].add(queue)
    failure = await bus.emit(job_id, "invented", {})
    assert failure.code == "CHECK_INCOMPLETE"
    assert not job_pool.events and queue.empty()
    failure = await bus.emit(job_id, "done", {"job_id": str(uuid4()), "status": "COMPLETE"})
    assert failure.code == "CHECK_INCOMPLETE"
    job_pool.fail_insert = True
    with pytest.raises(asyncpg.PostgresConnectionError):
        await bus.emit(job_id, "stage", events[0]["payload"])
    assert job_pool.rows[job_id]["status"] == "QUEUED" and queue.empty()
    job_pool.fail_insert = False
    job_pool.fail_commit = True
    with pytest.raises(asyncpg.PostgresConnectionError):
        await bus.emit(job_id, "stage", events[0]["payload"])
    assert not job_pool.events and queue.empty()
    assert job_pool.rows[job_id]["status"] == "QUEUED"
    job_pool.fail_commit = False
    event = await bus.emit(job_id, "stage", events[0]["payload"])
    assert event.seq == 1 and queue.get_nowait() == event
    failure = await bus.emit(uuid4(), "stage", events[0]["payload"])
    assert failure.code == "job_not_found"
    await bus.emit(job_id, "done", {"job_id": str(job_id), "status": "COMPLETE"})
    assert isinstance(await bus.emit(job_id, "stage", events[0]["payload"]), JobFailure)


async def test_storage_failures_are_redacted(job_client, job_app, monkeypatch, intake):
    monkeypatch.setattr(
        job_app.state.event_bus.jobs,
        "create",
        AsyncMock(side_effect=asyncpg.PostgresConnectionError("private credentials")),
    )
    response = await job_client.post("/jobs", json=intake["doi"])
    assert response.status_code == 503 and "private" not in response.text
    job_app.state.event_bus = None
    for path, method in [
        ("/jobs", "POST"),
        (f"/jobs/{uuid4()}", "GET"),
        (f"/jobs/{uuid4()}/events", "GET"),
        ("/dev/fake-job", "POST"),
    ]:
        response = await job_client.request(method, path)
        assert response.status_code == 503 and response.json()["code"] == "CHECK_INCOMPLETE"


def test_identifier_validator_and_openapi(job_app):
    with pytest.raises(ValidationError):
        jobs.Identifier(doi="x", arxiv_id="y")
    schema = job_app.openapi()
    content = schema["paths"]["/jobs"]["post"]["requestBody"]["content"]
    assert set(content) == {"multipart/form-data", "application/json"}
    assert content["multipart/form-data"]["schema"]["required"] == ["file"]
    assert "JobSnapshot" in schema["components"]["schemas"]
    assert (
        "text/event-stream"
        in schema["paths"]["/jobs/{job_id}/events"]["get"]["responses"]["200"]["content"]
    )


async def test_request_validation_and_method_errors(job_client):
    response = await job_client.get("/jobs/not-a-uuid")
    assert response.status_code == 400 and response.json()["code"] == "invalid_request"
    response = await job_client.delete("/jobs")
    assert response.status_code == 405 and set(response.json()) == {"code", "message"}


async def test_pdf_storage_failure_cleans_temporary_file(job_client, job_app, monkeypatch):
    data = (FIXTURES / "pdfs" / "1_pages.pdf").read_bytes()

    def fail_replace(*args):
        raise OSError("private credentials")

    monkeypatch.setattr(jobs.os, "replace", fail_replace)
    response = await job_client.post("/jobs", files={"file": ("paper.pdf", data)})
    assert response.status_code == 503 and "private" not in response.text
    assert not list((job_app.state.settings.data_dir / "uploads").iterdir())


async def test_stream_storage_failure_removes_subscriber(job_pool, monkeypatch):
    bus = EventBus(Jobs(job_pool))
    job_id = await bus.jobs.create("storage-failure-ip", {})
    monkeypatch.setattr(
        bus.jobs,
        "read_events",
        AsyncMock(side_effect=asyncpg.PostgresConnectionError("private credentials")),
    )
    assert [frame async for frame in bus.stream(job_id)] == []
    assert not bus.subscribers


async def test_fake_job_failure_and_shutdown(job_app, job_pool, monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "DEMO_FIXTURE", tmp_path / "missing.json")
    bus = EventBus(Jobs(job_pool))
    job_id = await bus.jobs.create("demo-failure-ip", {}, running=True)
    await demo.run_fake_job(bus, job_id)
    assert job_pool.rows[job_id]["status"] == "CHECK_INCOMPLETE"
    assert (await bus.jobs.read_events(job_id, 0))[-1].type == "done"
    monkeypatch.setattr(demo, "DEMO_FIXTURE", FIXTURES / "events" / "job.json")
    async with job_app.router.lifespan_context(job_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=job_app), base_url="http://test"
        ) as client:
            response = await client.post("/dev/fake-job")
            active_id = UUID(response.json()["job_id"])
            # Let the detached task enter its first sleep, then cancel via shutdown.
            await asyncio.sleep(0)
            assert job_pool.rows[active_id]["status"] == "RUNNING"
    assert job_pool.rows[active_id]["status"] == "CHECK_INCOMPLETE"
    assert not job_app.state.tasks
    job_pool.close.assert_awaited_once()
