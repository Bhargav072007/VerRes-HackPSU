import asyncio
import json
from time import monotonic
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

from api.app import main
from api.app.db import JobFailure, Jobs
from api.app.graph.service import GraphService
from api.app.ingest.service import IngestService
from api.app.orchestrator import Pipeline, Runner, build_services
from api.app.resolve.service import ResolveService
from api.app.review import ReviewStub
from api.app.routes.jobs import PDF_LIMIT, load_pdf, save_pdf
from api.app.settings import Settings
from api.app.sources.service import SourceService
from api.app.sse import EventBus
from api.app.stubs import FixtureServices
from api.app.verify.service import VerifyService
from tests.conftest import FIXTURES
from tests.test_jobs import frames


@pytest.fixture
async def pipeline(job_pool, tmp_path):
    settings = Settings(_env_file=None, env="test", data_dir=tmp_path)
    bus = EventBus(Jobs(job_pool))
    job_input = save_pdf((FIXTURES / "pdfs/1_pages.pdf").read_bytes(), tmp_path)
    job_id = await bus.jobs.create("pipeline-ip", job_input)
    services = build_services(settings)
    yield Pipeline(bus, services, settings), job_id
    await services.aclose()


async def test_factory_real_services_when_flag_unset(monkeypatch):
    monkeypatch.delenv("STUBS")
    services = build_services(Settings(_env_file=None))
    try:
        backend = services.backend
        for field, expected in (
            ("ingest", IngestService),
            ("resolve", ResolveService),
            ("sources", SourceService),
            ("verify", VerifyService),
            ("graph", GraphService),
        ):
            assert isinstance(getattr(backend, field), expected)
        assert isinstance(services.review, ReviewStub)
    finally:
        await services.aclose()
    assert all(client.is_closed for client in backend.gateway.clients.values())


async def test_post_stream_complete_run(job_pool, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    app = main.create_app(Settings(_env_file=None, env="test", data_dir=tmp_path))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        started = monotonic()
        response = await client.post(
            "/jobs", files={"file": ("paper.pdf", (FIXTURES / "pdfs/1_pages.pdf").read_bytes())}
        )
        assert response.status_code == 202
        job_id = UUID(response.json()["job_id"])
        streamed = await asyncio.wait_for(client.get(f"/jobs/{job_id}/events"), 15)
        received = frames(streamed.content)
        assert monotonic() - started < 15
        assert received[-1]["event"] == "done"
        assert [int(frame["id"]) for frame in received] == list(range(1, len(received) + 1))
        events = await app.state.event_bus.jobs.read_events(job_id, 0)
        assert sum(e.type == "review" for e in events) == 3
        assert sum(e.type == "support" for e in events) == 4
        assert events[-1].payload.review.warning == "Review panel is a stub until A8."
        stage_state = {}
        for event in events:
            if event.type == "stage":
                stage_state[event.payload.stage] = event.payload.status
        assert set(stage_state.values()) == {"COMPLETED"}
        assert events[-1].payload.status == "NEEDS_REVIEW"
        for ref in events[-1].payload.paper.references:
            chain = [e.type for e in events if getattr(e.payload, "reference_id", None) == ref.id]
            assert chain == ["existence", "retraction", "source"]
        kinds = [event.type for event in events]
        assert max(i for i, kind in enumerate(kinds) if kind == "support") < kinds.index("review")
        assert kinds.index("review_summary") < kinds.index("claim_map") < kinds.index("done")
        snapshot = (await client.get(f"/jobs/{job_id}")).json()
        assert len(snapshot["support"]) == 4
        assert isinstance(app.state.services.backend, FixtureServices)
    assert not app.state.tasks


@pytest.mark.parametrize(
    "method,kind",
    [
        ("resolve_reference", "existence"),
        ("check_retraction", "retraction"),
        ("fetch_source", "source"),
        ("verify_citation", "support"),
    ],
)
@pytest.mark.parametrize("invalid", [False, True])
async def test_row_failure_isolation(pipeline, monkeypatch, caplog, method, kind, invalid):
    runner, job_id = pipeline
    backend = runner.services.backend
    original = getattr(backend, method)

    async def faulty(row, *args):
        row_id = getattr(row, "reference_id", getattr(row, "id", None))
        if row_id == "ref-1":
            if invalid:
                return {"private": "secret response"}
            raise RuntimeError("secret provider credentials")
        return await original(row, *args)

    monkeypatch.setattr(backend, method, faulty)
    await runner.run_job(job_id)
    report = runner.report
    assert report.status == "NEEDS_REVIEW"
    assert len(report.support) == 4
    assert next(r for r in report.support if r.citation_id == "cite-2").label == "NOT_SUPPORTED"
    events = await runner.bus.jobs.read_events(job_id, 0)
    failed = [
        e
        for e in events
        if e.type == kind
        and (
            getattr(e.payload, "reference_id", None) == "ref-1"
            or getattr(e.payload, "citation_id", None) in ("cite-1", "cite-4")
        )
    ]
    assert failed and all("failed" in e.payload.reason for e in failed)
    assert events[-1].type == "done"
    assert f"job_id={job_id}" in caplog.text and "ref_id=ref-1" in caplog.text
    assert "secret" not in caplog.text + report.model_dump_json()


async def test_no_reference_or_graph_barrier(pipeline, monkeypatch):
    runner, job_id = pipeline
    backend, review = runner.services.backend, runner.services.review
    resolve, verify, graph, panel = (
        backend.resolve_reference,
        backend.verify_citation,
        backend.build_claim_map,
        review.run_review_panel,
    )
    verified, reviewed = asyncio.Event(), asyncio.Event()

    async def slow_reference(reference):
        if reference.id == "ref-1":
            await verified.wait()
        return await resolve(reference)

    async def signal_verification(citation, source):
        result = await verify(citation, source)
        if citation.id == "cite-2":
            verified.set()
        return result

    async def slow_graph(paper):
        await reviewed.wait()
        return await graph(paper)

    async def signal_review(paper, support):
        reviewed.set()
        return await panel(paper, support)

    monkeypatch.setattr(backend, "resolve_reference", slow_reference)
    monkeypatch.setattr(backend, "verify_citation", signal_verification)
    monkeypatch.setattr(backend, "build_claim_map", slow_graph)
    monkeypatch.setattr(review, "run_review_panel", signal_review)
    await asyncio.wait_for(runner.run_job(job_id), 2)
    assert runner.report.status == "NEEDS_REVIEW" and reviewed.is_set()


async def test_deadline_preserves_receipts_and_cancels_work(pipeline, monkeypatch):
    runner, job_id = pipeline
    original = runner.services.backend.resolve_reference
    cancelled = asyncio.Event()

    async def slow(reference):
        if reference.id != "ref-1":
            return await original(reference)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(runner.services.backend, "resolve_reference", slow)
    runner.deadline = 0.2
    await runner.run_job(job_id)
    assert cancelled.is_set()
    assert runner.report.status == "CHECK_INCOMPLETE"
    assert runner.report.reason == "timed out"
    assert len(runner.report.existence) == 3 and len(runner.report.support) == 4
    support = {r.citation_id: r for r in runner.report.support}
    assert (
        support["cite-1"].needs_review_reason
        == support["cite-4"].needs_review_reason
        == "timed out"
    )
    assert support["cite-2"].label == "NOT_SUPPORTED"
    assert (
        next(r for r in runner.report.retractions if r.reference_id == "ref-1").status == "UNKNOWN"
    )
    assert not runner.pending
    assert (await runner.bus.jobs.read_events(job_id, 0))[-1].type == "done"


@pytest.mark.parametrize(
    "method", ["scan_hidden_text", "build_claim_map", "prepare", "run_review_panel"]
)
async def test_nonrow_failure_continues(pipeline, monkeypatch, method):
    runner, job_id = pipeline
    target = (
        runner.services.review
        if method in ("prepare", "run_review_panel")
        else runner.services.backend
    )
    monkeypatch.setattr(target, method, AsyncMock(side_effect=RuntimeError("private")))
    await runner.run_job(job_id)
    assert len(runner.report.support) == 4
    assert runner.report.status == "NEEDS_REVIEW"
    assert (await runner.bus.jobs.read_events(job_id, 0))[-1].type == "done"


async def test_parse_failure_stops_job(pipeline, monkeypatch):
    runner, job_id = pipeline
    monkeypatch.setattr(runner.services.backend, "parse_pdf", AsyncMock(return_value=None))
    await runner.run_job(job_id)
    events = await runner.bus.jobs.read_events(job_id, 0)
    assert runner.report.status == "CHECK_INCOMPLETE"
    assert not any(e.type in ("existence", "support", "paper") for e in events)
    assert events[-1].type == "done"


async def test_startup_recovery_and_idempotent_rows(pipeline, job_pool, monkeypatch):
    pipeline_runner, job_id = pipeline
    bus = pipeline_runner.bus
    await bus.emit(job_id, "stage", {"stage": "parse_pdf", "status": "STARTED"})
    fixture = json.loads((FIXTURES / "pipeline/paper1.json").read_text())
    await bus.emit(job_id, "paper", fixture["paper"])
    await bus.emit(job_id, "existence", fixture["existence"][0])
    await bus.emit(
        job_id,
        "hidden_text",
        {
            "id": "scan-incomplete",
            "kind": "CHECK_INCOMPLETE",
            "quote": "",
            "reason": "old attempt failed",
        },
    )
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    app = main.create_app(pipeline_runner.settings)
    async with app.router.lifespan_context(app):
        runner = app.state.runner
        first = runner.start(job_id)
        assert first is runner.start(job_id) and len(app.state.tasks) == 1
        await first
        await asyncio.sleep(0)
        assert not runner.active and not app.state.tasks and not job_pool.leases
        assert len([key for key in job_pool.results if key[1] == "existence"]) == 3
        await runner.run_job(job_id)  # terminal jobs are never rerun
        assert sum(e["type"] == "done" for e in job_pool.events) == 1
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            snapshot = (await client.get(f"/jobs/{job_id}")).json()
        assert len(snapshot["existence"]) == 3 and len(snapshot["support"]) == 4
        assert [finding["id"] for finding in snapshot["hidden_text"]] == ["hidden-1"]


async def test_cancelled_job_can_be_recovered(pipeline, job_pool, monkeypatch):
    pipeline_runner, job_id = pipeline
    runner = Runner(pipeline_runner.bus, pipeline_runner.services, pipeline_runner.settings, set())
    entered = asyncio.Event()
    original = runner.services.backend.resolve_reference

    async def paused(reference):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(runner.services.backend, "resolve_reference", paused)
    task = runner.start(job_id)
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert job_pool.rows[job_id]["status"] == "RUNNING" and not job_pool.leases
    monkeypatch.setattr(runner.services.backend, "resolve_reference", original)
    await runner.recover()
    await asyncio.gather(*runner.active.values())
    assert job_pool.rows[job_id]["status"] == "NEEDS_REVIEW"
    assert sum(e["type"] == "done" for e in job_pool.events) == 1


async def test_lease_prevents_duplicate_workers(pipeline, job_pool):
    pipeline_runner, job_id = pipeline
    runner = Runner(pipeline_runner.bus, pipeline_runner.services, pipeline_runner.settings, set())
    async with pipeline_runner.bus.jobs.lease(job_id) as acquired:
        assert acquired
        await runner.run_job(job_id)
        assert not job_pool.events
    assert not job_pool.leases


async def test_admission_race_keeps_job_scheduled(pipeline, monkeypatch):
    pipeline_runner, job_id = pipeline
    bus = pipeline_runner.bus
    original = bus.emit
    attempts = 0

    async def busy_once(job_id, kind, payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return JobFailure(code="rate_limited", message="Three jobs are already running.")
        return await original(job_id, kind, payload)

    monkeypatch.setattr(bus, "emit", busy_once)
    runner = Runner(bus, pipeline_runner.services, pipeline_runner.settings, set())
    await asyncio.wait_for(runner.start(job_id), 2)
    assert (await bus.jobs.read_events(job_id, 0))[-1].type == "done"


@pytest.mark.parametrize(
    "case", ["good", "oversize", "stream_oversize", "invalid_pdf", "http_error", "bad_id", "doi"]
)
async def test_identifier_intake(pipeline, respx_mock, monkeypatch, case):
    runner, job_id = pipeline
    body = (FIXTURES / "pdfs/1_pages.pdf").read_bytes()
    headers = {"content-length": str(PDF_LIMIT + 1)} if case == "oversize" else {}
    if case == "stream_oversize":
        monkeypatch.setattr("api.app.routes.jobs.PDF_LIMIT", 100)
    route = respx_mock.get("https://arxiv.org/pdf/2401.12345").respond(
        503 if case == "http_error" else 200,
        content=b"not pdf" if case == "invalid_pdf" else body,
        headers=headers,
    )
    job_input = {"arxiv_id": "2401.12345"}
    if case == "bad_id":
        job_input = {"arxiv_id": "../../unsafe"}
    elif case == "doi":
        job_input = {"doi": "10.1234/example"}
    result = await load_pdf(job_input, runner.settings)
    assert isinstance(result, bytes) == (case == "good")
    assert route.called == (case not in ("bad_id", "doi"))
    if case == "doi":
        assert result.message == "DOI intake not yet supported"


async def test_doi_job_emits_error_and_done(pipeline, job_pool):
    runner, job_id = pipeline
    job_pool.rows[job_id]["input"] = {"doi": "10.1234/example"}
    await runner.run_job(job_id)
    events = await runner.bus.jobs.read_events(job_id, 0)
    assert events[-2].type == "stage" and events[-1].type == "done"
    assert (
        next(e for e in events if e.type == "error").payload.reason
        == "DOI intake not yet supported"
    )
    assert runner.report.status == "CHECK_INCOMPLETE"


def test_generated_replay_fixture():
    from api.app.db import EVENTS

    events = [
        EVENTS.validate_json(line)
        for line in (FIXTURES / "events/paper1.jsonl").read_text().splitlines()
    ]
    assert events[-1].type == "done" and len(events[-1].payload.support) == 4
    assert sum(event.type == "review" for event in events) == 3
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
