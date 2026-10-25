"""Offline proof through intake, the real runner, journal, snapshots, and SSE.

STUBS=1 uses paper1.json for every PDF; paper 2/3 exercise upload/completion,
not their semantic findings. PostgreSQL transport is fixture-backed.
"""

import asyncio
import hashlib
import json
import socket
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest

from api.app import main
from api.app.db import EVENTS
from api.app.settings import Settings
from tests.conftest import FIXTURES
from tests.test_jobs import frames


@pytest.fixture
async def offline_app(monkeypatch, tmp_path, job_pool):
    monkeypatch.setenv("STUBS", "1")
    monkeypatch.setenv("DEMO_FIXTURE", "0")
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    # Count attempts as well as blocking them: pipeline fallbacks must not hide I/O.
    network = Mock(side_effect=AssertionError("Offline e2e attempted network I/O"))
    async_http = AsyncMock(side_effect=AssertionError("Offline e2e attempted HTTP"))
    for method in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, method, network)
    monkeypatch.setattr(socket, "getaddrinfo", network)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_http)
    app = main.create_app(Settings(_env_file=None, env="test", data_dir=tmp_path))
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            yield app, client
        assert not app.state.tasks
        assert not app.state.runner.active
        assert not app.state.event_bus.subscribers
        assert not job_pool.leases
        job_pool.close.assert_awaited_once()
    finally:
        network.assert_not_called()
        async_http.assert_not_called()


@pytest.mark.parametrize(
    "pdf_name",
    ["paper1_attention.pdf", "paper2_retracted_reference.pdf", "paper3_planted_problems.pdf"],
    ids=["paper1-proof", "paper2-smoke", "paper3-smoke"],
)
async def test_stubs_full_run_offline(offline_app, job_pool, pdf_name):
    app, client = offline_app
    data = (FIXTURES / "pdfs" / pdf_name).read_bytes()
    accepted = await client.post("/jobs?fresh=true", files={"file": (pdf_name, data)})
    assert accepted.status_code == 202
    job_id = UUID(accepted.json()["job_id"])
    streamed = await asyncio.wait_for(client.get(f"/jobs/{job_id}/events"), timeout=15)
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    received = frames(streamed.content)
    events = [
        EVENTS.validate_python(
            {
                "job_id": job_id,
                "seq": int(frame["id"]),
                "type": frame["event"],
                "payload": json.loads(frame["data"]),
            }
        )
        for frame in received
    ]
    assert events == await app.state.event_bus.jobs.read_events(job_id, 0)
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert events[-1].type == "done"
    assert sum(event.type == "done" for event in events) == 1
    assert not any(event.type == "error" for event in events)
    stages = [event.payload for event in events if event.type == "stage"]
    assert {stage.status for stage in stages} == {"STARTED", "COMPLETED"}
    assert {stage.stage for stage in stages if stage.status == "STARTED"} == {
        stage.stage for stage in stages if stage.status == "COMPLETED"
    }

    report = events[-1].payload
    expected = json.loads((FIXTURES / "pipeline/paper1.json").read_text())
    assert report.status == "NEEDS_REVIEW"  # Unresolved fixture evidence stays visible.
    assert report.paper.model_dump(mode="json", exclude_defaults=True) == expected["paper"]
    assert report.pdf_sha256 == hashlib.sha256(data).hexdigest()
    assert report.started_at <= report.finished_at
    row = job_pool.rows[job_id]
    assert row["status"] == report.status
    assert row["input"]["sha256"] == report.pdf_sha256
    assert not row["demo_fixture"] and not row.get("replay_of")

    reference_ids = {reference.id for reference in report.paper.references}
    citation_ids = {citation.id for citation in report.paper.citations}
    assert reference_ids and citation_ids
    for field, kind, id_field, expected_ids in (
        ("existence", "existence", "reference_id", reference_ids),
        ("retractions", "retraction", "reference_id", reference_ids),
        ("sources", "source", "reference_id", reference_ids),
        ("support", "support", "citation_id", citation_ids),
    ):
        results = getattr(report, field)
        assert len(results) == len(expected_ids)
        assert {getattr(result, id_field) for result in results} == expected_ids
        emitted = [event.payload for event in events if event.type == kind]
        assert sorted(result.model_dump_json() for result in emitted) == sorted(
            result.model_dump_json() for result in results
        )
        assert {key[2] for key in job_pool.results if key[:2] == (job_id, kind)} == expected_ids

    assert {comment.reviewer for comment in report.review.comments} == {
        "METHODS",
        "EVIDENCE",
        "CLAIMS",
    }
    assert report.review.top_fixes and report.review.warning
    assert [event.payload for event in events if event.type == "review"] == report.review.comments
    assert [event.payload for event in events if event.type == "review_summary"] == [report.review]
    assert report.claim_map.paper_id == report.paper.id
    assert report.claim_map.nodes and report.claim_map.status == "COMPLETE"
    assert [event.payload for event in events if event.type == "claim_map"] == [report.claim_map]
    assert [event.payload for event in events if event.type == "hidden_text"] == report.hidden_text

    # Receipts remain traceable to the matching source and paper sentences.
    sources = {source.reference_id: source for source in report.sources}
    citations = {citation.id: citation for citation in report.paper.citations}
    for result in report.support:
        passages = {
            passage.passage_id: passage.text
            for passage in sources[citations[result.citation_id].reference_id].passages
        }
        for evidence in result.evidence:
            assert evidence.quote in passages[evidence.passage_id]
    sentences = {sentence.id: sentence.text for sentence in report.paper.sentences}
    for comment in report.review.comments:
        assert any(comment.quote in sentences[sentence_id] for sentence_id in comment.sentence_ids)

    snapshot = await client.get(f"/jobs/{job_id}")
    assert snapshot.status_code == 200
    # Snapshot provenance adds source URLs and derives timings from the journal.
    for field in ("job_id", "status", "pdf_sha256", "paper", "review", "claim_map", "hidden_text"):
        assert snapshot.json()[field] == report.model_dump(mode="json")[field]
