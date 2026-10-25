import asyncio
import hashlib
import json
import logging
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

from api.app import main, version
from api.app.db import Jobs, cache_key
from api.app.orchestrator import Pipeline
from api.app.providers.http import Policy
from api.app.review.runtime import (
    DemoCircuit,
    JSONFormatter,
    ResilientGateway,
    job_context,
    model_cost,
    provider_issues,
    stage_context,
)
from api.app.routes import demo
from api.app.routes.jobs import normalize_identifier
from api.app.settings import Settings
from tests import test_jobs
from tests.conftest import FIXTURES
from tests.test_jobs import frames

job_app = test_jobs.job_app
job_client = test_jobs.job_client


async def test_cache_new_job_id_replays_owned_receipts(job_client, job_app, events):
    accepted = await job_client.post("/jobs", json={"arxiv_id": "2401.12345"})
    original = UUID(accepted.json()["job_id"])
    for event in events:
        payload = deepcopy(event["payload"])
        if event["type"] == "done":
            payload["job_id"] = str(original)
        await job_app.state.event_bus.emit(original, event["type"], payload)
    starts = job_app.state.runner.start.call_count
    cached = await job_client.post("/jobs", json={"arxiv_id": "https://arxiv.org/abs/2401.12345"})
    cached_id = cached.json()["job_id"]
    assert cached_id != str(original)
    assert job_app.state.runner.start.call_count == starts
    snapshot = (await job_client.get(f"/jobs/{cached_id}")).json()
    assert snapshot["job"]["replay_of"] == str(original)
    assert snapshot["status"] == "COMPLETE"
    assert all(event["job_id"] == cached_id for event in snapshot["events"])
    received = frames((await job_client.get(f"/jobs/{cached_id}/events")).content)
    assert json.loads(received[-1]["data"])["job_id"] == cached_id
    assert "demo_fixture" not in json.loads(received[-1]["data"])
    for _ in range(6):
        assert (await job_client.post("/jobs", json={"arxiv_id": "2401.12345"})).status_code == 202
    fresh = await job_client.post("/jobs?fresh=1", json={"arxiv_id": "2401.12345"})
    assert (await job_client.get(f"/jobs/{fresh.json()['job_id']}")).json()["status"] == "QUEUED"


@pytest.mark.parametrize("miss", ["input", "version", "incomplete", "fixture"])
async def test_cache_misses(job_pool, events, monkeypatch, miss):
    jobs = Jobs(job_pool)
    original = await jobs.create("original", {"sha256": "a" * 64}, demo_fixture=miss == "fixture")
    report = deepcopy(events[-1]["payload"])
    report["job_id"] = str(original)
    if miss == "incomplete":
        report["status"] = "CHECK_INCOMPLETE"
    await jobs.append(original, "done", report)
    if miss == "version":
        monkeypatch.setattr(version, "PIPELINE_VERSION", "next")
    new = await jobs.create("new", {"sha256": ("b" if miss == "input" else "a") * 64})
    assert (await jobs.get(new))["status"] == "QUEUED"
    assert not await jobs.read_events(new, 0)


@pytest.mark.parametrize(
    "kind,value,canonical",
    [
        ("doi", "https://doi.org/10.1234/ABC", "10.1234/abc"),
        ("doi", "DOI: 10.1234/abc", "10.1234/abc"),
        ("arxiv_id", "https://arxiv.org/pdf/1706.03762v2.pdf", "1706.03762v2"),
        ("arxiv_id", "arXiv: 1706.03762v1", "1706.03762v1"),
    ],
)
def test_identifier_cache_normalization(kind, value, canonical):
    normalized = normalize_identifier({kind: value})
    assert normalized == {kind: canonical}
    assert cache_key(normalized) == cache_key({kind: canonical})
    assert cache_key({"demo": "fixture"}) is None


@pytest.mark.parametrize("paper", demo.DEMO_PAPERS)
async def test_fixture_missing_is_explicit_and_never_runs_providers(
    job_client, job_app, tmp_path, monkeypatch, paper
):
    monkeypatch.setattr(demo, "RECORDINGS", tmp_path / "demo")
    (tmp_path / "pdfs").symlink_to(FIXTURES / "pdfs", target_is_directory=True)
    job_app.state.demo_fixture = True
    response = await job_client.post(
        "/jobs", files={"file": ("paper.pdf", (FIXTURES / f"pdfs/{paper}.pdf").read_bytes())}
    )
    job_id = UUID(response.json()["job_id"])
    services = job_app.state.services
    monkeypatch.setattr(
        services.backend, "parse_pdf", AsyncMock(side_effect=AssertionError("must not run"))
    )
    await Pipeline(job_app.state.event_bus, services, job_app.state.settings).run_job(job_id)
    snapshot = (await job_client.get(f"/jobs/{job_id}")).json()
    assert snapshot["demo_fixture"] is True
    assert snapshot["status"] == "CHECK_INCOMPLETE"
    assert "recording missing" in snapshot["reason"]
    received = frames((await job_client.get(f"/jobs/{job_id}/events")).content)
    assert all(json.loads(frame["data"])["demo_fixture"] for frame in received)
    services.backend.parse_pdf.assert_not_awaited()


async def test_fixture_replay_and_resume(job_client, job_app, events, tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "RECORDINGS", tmp_path / "demo")
    (tmp_path / "demo").mkdir()
    (tmp_path / "pdfs").symlink_to(FIXTURES / "pdfs", target_is_directory=True)
    data = (FIXTURES / "pdfs/paper1_attention.pdf").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    # Test-only simulated recording; never shipped as a real demo recording.
    recording = deepcopy(events[:-1])  # Legacy test fixture has an error after done.
    for event in recording:
        event["input_sha256"] = digest
    (tmp_path / "demo/paper1.jsonl").write_text("\n".join(json.dumps(e) for e in recording))
    job_app.state.demo_fixture = True
    response = await job_client.post("/jobs", files={"file": ("paper.pdf", data)})
    job_id = UUID(response.json()["job_id"])
    await Pipeline(job_app.state.event_bus, job_app.state.services, job_app.state.settings).run_job(
        job_id
    )
    snapshot = (await job_client.get(f"/jobs/{job_id}")).json()
    assert snapshot["demo_fixture"] and all(
        e["payload"]["demo_fixture"] for e in snapshot["events"]
    )
    response = await job_client.get(f"/jobs/{job_id}/events", headers={"Last-Event-ID": "2"})
    replay = frames(response.content)
    assert replay[0]["id"] == "3" and replay[-1]["event"] == "done"
    assert json.loads(replay[-1]["data"])["job_id"] == str(job_id)
    assert json.loads(replay[-1]["data"])["demo_fixture"]
    created = (await job_client.post(f"/jobs/{job_id}/share")).json()
    shared_path = f"/shares/{created['token']}"
    public = (await job_client.get(shared_path)).json()
    assert public["demo_fixture"] is True
    assert "job" not in public and "events" not in public
    assert "sentences" not in public["paper"]
    assert all("passages" not in source for source in public["sources"])
    exported = await job_client.get(shared_path + "/export?format=md")
    assert exported.headers["content-type"].startswith("text/markdown")
    assert "Demo fixture: true" in exported.text


async def test_fixture_toggle_preserves_real_job_journal(
    job_client, job_app, tmp_path, monkeypatch
):
    monkeypatch.setattr(demo, "RECORDINGS", tmp_path / "demo")
    (tmp_path / "pdfs").symlink_to(FIXTURES / "pdfs", target_is_directory=True)
    data = (FIXTURES / "pdfs/paper1_attention.pdf").read_bytes()
    accepted = await job_client.post("/jobs", files={"file": ("paper.pdf", data)})
    job_id = accepted.json()["job_id"]
    job_app.state.demo_fixture = True
    snapshot = (await job_client.get(f"/jobs/{job_id}")).json()
    assert snapshot["demo_fixture"] and "recording missing" in snapshot["reason"]
    replay = frames((await job_client.get(f"/jobs/{job_id}/events")).content)
    assert json.loads(replay[-1]["data"])["demo_fixture"]
    job_app.state.demo_fixture = False
    snapshot = (await job_client.get(f"/jobs/{job_id}")).json()
    assert "demo_fixture" not in snapshot and snapshot["status"] == "QUEUED"
    assert not snapshot["events"]


@pytest.mark.parametrize("bad", [[], [{}], "invalid", [{"payload": {}}]])
def test_invalid_recordings_are_reviewable(bad):
    assert isinstance(demo.validate_recording(bad), str)


async def test_five_concurrent_jobs_queue_and_complete(job_pool, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    app = main.create_app(Settings(_env_file=None, env="test", data_dir=tmp_path))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        data = (FIXTURES / "pdfs/1_pages.pdf").read_bytes()
        accepted = await asyncio.gather(
            *(client.post("/jobs?fresh=1", files={"file": ("paper.pdf", data)}) for _ in range(5))
        )
        assert all(result.status_code == 202 for result in accepted)
        replies = await asyncio.wait_for(
            asyncio.gather(*(client.get(f"/jobs/{r.json()['job_id']}/events") for r in accepted)),
            15,
        )
        assert all(frames(reply.content)[-1]["event"] == "done" for reply in replies)
        assert all(row["status"] == "NEEDS_REVIEW" for row in job_pool.rows.values())


async def test_status_shape_and_accounting(job_client, job_app, job_pool):
    await job_app.state.event_bus.jobs.record_spend(None, 0.15)
    response = await job_client.get("/status")
    assert response.status_code == 200
    value = response.json()
    assert value["uptime_seconds"] >= 0 and value["git_sha"] == version.GIT_SHA
    assert value["pipeline_version"] == version.PIPELINE_VERSION
    assert value["jobs_last_hour"] == 0 and value["avg_duration_seconds"] is None
    assert set(value["providers"]) >= {"crossref", "openalex", "arxiv", "model"}
    assert value["llm"]["spend_usd"] == 0.15
    assert value["llm"]["daily_budget_usd"] == job_app.state.settings.llm_daily_budget
    assert "database_url" not in response.text and "api_key" not in response.text
    await job_app.state.event_bus.jobs.record_spend(None, None)
    response = await job_client.get("/status")
    assert response.status_code == 200 and response.json()["llm"]["spend_usd"] == 0.15
    assert response.json()["llm"]["accounting"] == "estimated"
    assert response.json()["llm"]["unknown_calls"] == 1
    assert response.json()["llm"]["known_spend_usd"] == 0.15
    job_app.state.event_bus = None
    response = await job_client.get("/status")
    assert response.status_code == 503 and response.json()["status"] == "CHECK_INCOMPLETE"


def test_breaker_three_failures_half_open_and_reset():
    circuit = DemoCircuit()
    for stamp in (0, 1, 2):
        assert circuit.enter(stamp)
        circuit.record(True, 503, stamp)
    assert not circuit.enter(61)
    assert circuit.enter(62) and not circuit.enter(62)
    circuit.record(True, 503, 62)
    assert not circuit.enter(121) and circuit.enter(122)
    circuit.record(False, 200, 122)
    assert circuit.enter(123) and circuit.failures == 0 and circuit.open_until == 0


async def test_gateway_timeout_and_shared_crossref_breaker(respx_mock):
    clock = [0]
    policies = {
        name: Policy("https://crossref.example", 100, 1, 3)
        for name in ("crossref_single", "crossref_query")
    }
    gateway = ResilientGateway(policies, attempts=1, clock=lambda: clock[0])
    route = respx_mock.get("https://crossref.example/works").respond(503)
    issues = []
    token = provider_issues.set(issues)
    try:
        for _ in range(3):
            await gateway.request("crossref_single", "/works")
        result = await gateway.request("crossref_query", "/works")
        assert route.call_count == 3 and "crossref: circuit open" in result.error
        assert all("crossref" in issue for issue in issues)
        assert gateway.breaker_states()["crossref"]["state"] == "OPEN"
        assert route.calls[0].request.extensions["timeout"]["read"] == 10
        clock[0] = 61
        route.respond(200, json={"message": "ok"})
        assert (await gateway.request("crossref_query", "/works")).status == 200
        assert gateway.breaker_states()["crossref"]["state"] == "CLOSED"
    finally:
        provider_issues.reset(token)
        await gateway.aclose()


async def test_stage_provider_failure_becomes_receipt(job_client, job_app, job_pool, monkeypatch):
    gateway = ResilientGateway(
        {"openalex": Policy("https://openalex.example", 100, 1, 1)}, attempts=1
    )

    async def outage(reference):
        gateway.note_issue("openalex", "circuit open; retry after 60s")
        return await original(reference)

    backend = job_app.state.services.backend
    original = backend.resolve_reference
    monkeypatch.setattr(backend, "resolve_reference", outage)
    accepted = await job_client.post(
        "/jobs", files={"file": ("paper.pdf", (FIXTURES / "pdfs/1_pages.pdf").read_bytes())}
    )
    runner = Pipeline(job_app.state.event_bus, job_app.state.services, job_app.state.settings)
    try:
        await runner.run_job(UUID(accepted.json()["job_id"]))
        assert all(
            row.status == "CHECK_INCOMPLETE" and "openalex: circuit open" in row.reason
            for row in runner.report.existence
        )
        assert runner.report.status == "NEEDS_REVIEW"
    finally:
        await gateway.aclose()


def test_log_formatter_contains_context_and_valid_json():
    job_token = job_context.set("job-1")
    stage_token = stage_context.set("existence:ref-1")
    try:
        record = logging.LogRecord("verres", logging.INFO, "", 0, "stage finished", (), None)
        record.duration_seconds = 1.2
        payload = json.loads(JSONFormatter().format(record))
        assert payload["job_id"] == "job-1" and payload["stage"] == "existence:ref-1"
        assert payload["duration_seconds"] == 1.2
    finally:
        job_context.reset(job_token)
        stage_context.reset(stage_token)


@pytest.mark.parametrize(
    "payload", [{}, {"usage": {}}, {"usage": {"prompt_tokens": True, "completion_tokens": 1}}]
)
def test_cost_unknown_is_not_zero(payload):
    assert model_cost(payload) == (None, True)


async def test_model_cost_persisted_and_budget_guard(job_pool, respx_mock, monkeypatch):
    monkeypatch.setenv("MODEL_PRICES", '{"fixture-model": [1, 2]}')
    payload = {
        "model": "fixture-model",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 2000},
    }
    assert model_cost(payload) == (0.005, False)
    route = respx_mock.post("https://model.example/complete").respond(200, json=payload)
    gateway = ResilientGateway(
        {"review": Policy("https://model.example", 100, 1, 1)},
        jobs=Jobs(job_pool),
        daily_budget_usd=0.005,
    )
    try:
        await gateway.request("review", "/complete", method="POST", timeout=100)
        result = await gateway.request("review", "/complete", method="POST")
        assert route.call_count == 1 and "budget" in result.error
        assert route.calls[0].request.extensions["timeout"]["read"] == 60
        assert (await Jobs(job_pool).llm_spend())["spend_usd"] == 0.005
    finally:
        await gateway.aclose()


async def test_missing_usage_blocks_further_model_spend(job_pool, respx_mock):
    route = respx_mock.post("https://model.example/complete").respond(200, json={"choices": []})
    gateway = ResilientGateway(
        {"review": Policy("https://model.example", 100, 1, 3)}, jobs=Jobs(job_pool)
    )
    try:
        result = await gateway.request("review", "/complete", method="POST")
        blocked = await gateway.request("review", "/complete", method="POST")
        assert result.status == 200 and "usage unavailable" in blocked.error
        assert route.call_count == 1
        assert (await Jobs(job_pool).llm_spend())["unknown_calls"] == 1
    finally:
        await gateway.aclose()


async def test_arxiv_intake_uses_resilient_boundary(respx_mock, tmp_path):
    from api.app.routes.jobs import load_pdf

    gateway = ResilientGateway(
        {"arxiv-intake": Policy("https://arxiv.example", 100, 1, 1)}, attempts=1
    )
    route = respx_mock.get("https://arxiv.example/pdf/1706.03762").respond(
        200, content=(FIXTURES / "pdfs/paper1_attention.pdf").read_bytes()
    )
    settings = Settings(_env_file=None, data_dir=tmp_path)
    try:
        data = await load_pdf({"arxiv_id": "1706.03762"}, settings, gateway=gateway)
        assert isinstance(data, bytes) and data.startswith(b"%PDF-")
        assert route.calls[0].request.extensions["timeout"]["read"] == 20
        route.respond(503)
        result = await load_pdf({"arxiv_id": "1706.03762"}, settings, gateway=gateway)
        assert result.code == "CHECK_INCOMPLETE" and "arxiv" in result.message
    finally:
        await gateway.aclose()
