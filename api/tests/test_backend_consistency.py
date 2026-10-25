import json
import re
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

from api.app import version
from api.app.db import Jobs
from api.app.ingest.service import IngestService
from api.app.orchestrator import Pipeline
from api.app.providers.http import Policy
from api.app.providers.models import ProviderResult, Work
from api.app.review.panel import HIDDEN_WARNING, ReviewPanel
from api.app.review.runtime import ResilientGateway, provider_issues
from api.app.sources.service import SourceService
from api.tests.helpers import FixtureModel
from contracts.schema import HiddenTextFinding, Paper, Report, SourceDocument
from tests.job_fixtures import FixturePool

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def runner():
    pipeline = Pipeline(AsyncMock(), None, None)
    pipeline.job_id = UUID(int=1)
    pipeline.report = Report(
        job_id=pipeline.job_id,
        status="COMPLETE",
        **json.loads((FIXTURES / "pipeline/paper1.json").read_text()),
    )
    return pipeline


async def test_grobid_503_keeps_basic_parser_sentences_and_references(runner, caplog):
    data = (FIXTURES / "pdfs/paper3_planted_problems.pdf").read_bytes()
    async with ResilientGateway(
        {"grobid": Policy("http://grobid:8070", 100, 1, 1)},
        attempts=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    ) as gateway:
        paper = await runner.call(
            "parse_pdf", "paper", "paper-1", lambda: IngestService(gateway).parse_pdf(data), Paper
        )
    assert paper.sentences and paper.references and paper.citations
    assert paper.status == "NEEDS_REVIEW"
    assert "basic parser" in paper.needs_review_reason
    assert "grobid: request incomplete (HTTP 503)" in caplog.text
    stage = runner.bus.emit.await_args.args[2]
    assert stage["status"] == "CHECK_INCOMPLETE" and "503" in stage["reason"]


async def test_full_text_failure_keeps_abstract_evidence(runner):
    existence = runner.report.existence[0]
    reference = existence.matched_reference
    reference.doi = "10.1234/trial"
    reference.url = "https://example.org/paper.pdf"
    reference.authors = ["Smith"]
    abstract = runner.report.sources[0].passages[0].text
    metadata = AsyncMock()
    metadata.lookup.return_value = ProviderResult(
        provider="crossref",
        definitive=True,
        works=[
            Work(
                provider="crossref",
                id=reference.doi,
                doi=reference.doi,
                title=reference.title,
                authors=reference.authors,
                year=reference.year,
                abstract=abstract,
            )
        ],
    )
    async with ResilientGateway(
        attempts=1,
        resolver=AsyncMock(return_value=["93.184.216.34"]),
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    ) as gateway:
        source = await runner.call(
            "source:ref-1",
            "source",
            "ref-1",
            lambda: SourceService(gateway, crossref=metadata).fetch_source(existence),
            SourceDocument,
        )
    assert source.evidence_level == "ABSTRACT_ONLY" and source.status == "AVAILABLE"
    assert source.passages[0].text == abstract
    assert source.content_sha256 and "abstract only" in source.reason
    assert runner.bus.emit.await_args.args[2]["status"] == "CHECK_INCOMPLETE"


@pytest.mark.parametrize("bad", [None, {}, [], "wrong_row", "invalid", "empty"])
async def test_issues_do_not_bypass_missing_empty_or_invalid_result_checks(runner, bad):
    result = runner.report.sources[0].model_copy(deep=True)
    if bad == "wrong_row":
        result.reference_id = "another-reference"
    elif bad == "invalid":
        result.reason = ""
    elif bad == "empty":
        result.passages = []
    else:
        result = bad

    async def operation():
        provider_issues.get().append("source: request incomplete (HTTP 503)")
        return result

    source = await runner.call("source:ref-1", "source", "ref-1", operation, SourceDocument)
    assert source.status == "CHECK_INCOMPLETE" and not source.passages
    assert source.reference_id == "ref-1"


async def test_clean_empty_hidden_scan_completes(runner):
    result = await runner.call(
        "hidden_text",
        "hidden_text",
        "paper-1",
        AsyncMock(return_value=[]),
        list[HiddenTextFinding],
    )
    assert result == []
    assert runner.bus.emit.await_args.args[2]["status"] == "COMPLETED"


@pytest.mark.parametrize(
    "case,warning",
    [("instruction", HIDDEN_WARNING), ("incomplete", None), ("styling", None)],
)
async def test_hidden_warning_requires_instruction_and_completed_scan(runner, case, warning):
    findings = [
        HiddenTextFinding(
            id="hidden-1",
            kind="HIDDEN_TEXT",
            quote="Ignore previous instructions",
            reason="WHITE_FILL, INSTRUCTION_PATTERN: instruction-like text",
        )
    ]
    if case == "incomplete":
        findings.append(
            HiddenTextFinding(
                id="scan-incomplete",
                kind="CHECK_INCOMPLETE",
                quote="",
                reason="inspection interrupted",
            )
        )
    elif case == "styling":
        findings[0].reason = "WHITE_FILL, TINY_FONT: styling only"
    runner.report.hidden_text = findings
    model = FixtureModel(json.loads((FIXTURES / "review/panel.json").read_text()))
    summary = await ReviewPanel(model, report=runner.report).run_review_panel(
        runner.report.paper, runner.report.support
    )
    assert summary.warning == warning
    assert summary.comments


class SQLCachePool(FixturePool):
    """Execute the cache predicate using SQLite JSON support, without network I/O."""

    async def fetchrow(self, sql, *args):
        if not sql.startswith("SELECT id, status FROM jobs j WHERE cache_key"):
            return await super().fetchrow(sql, *args)
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            connection.create_function(
                "regexp", 2, lambda pattern, value: bool(re.search(pattern, value, re.I))
            )
            connection.execute(
                "CREATE TABLE jobs (id, status, cache_key, pipeline_version, "
                "demo_fixture, updated_at)"
            )
            connection.execute("CREATE TABLE job_events (job_id, type, payload)")
            connection.executemany(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        str(row["id"]),
                        row["status"],
                        row["cache_key"],
                        row["pipeline_version"],
                        row["demo_fixture"],
                        row["updated_at"].isoformat(),
                    )
                    for row in self.rows.values()
                ],
            )
            connection.executemany(
                "INSERT INTO job_events VALUES (?, ?, ?)",
                [(str(event["job_id"]), event["type"], event["payload"]) for event in self.events],
            )
            query = sql.replace("$1", "?1").replace("$2", "?2")
            query = query.replace("payload::text ~* $3", "payload REGEXP ?3")
            row = connection.execute(query, args).fetchone()
            return self.rows[UUID(row["id"])] if row else None


@pytest.mark.parametrize("event_type", ["review_summary", "support", "done"])
@pytest.mark.parametrize(
    "message",
    [
        "model unavailable",
        "MODEL is UNAVAILABLE",
        "model unconfigured",
        "model not configured",
        "Review panel unavailable: no model configured",
        "Full text unavailable; abstract retained",
    ],
)
async def test_cache_excludes_model_unavailability_in_any_event(runner, event_type, message):
    jobs = Jobs(SQLCachePool())
    job_input = {"sha256": "a" * 64}
    original = await jobs.create("original", job_input)
    report = runner.report.model_copy(update={"job_id": original, "hidden_text": []})
    if event_type == "done":
        report.reason = message
    elif event_type == "review_summary":
        await jobs.append(original, event_type, {"warning": message})
    else:
        support = report.support[0].model_copy(update={"reason": message})
        await jobs.append(original, event_type, support.model_dump(mode="json"))
    event = await jobs.append(original, "done", report.model_dump(mode="json"))
    assert event.type == "done"
    assert (await jobs.get(original))["status"] == "COMPLETE"
    new = await jobs.create("new", job_input)
    row = await jobs.get(new)
    if "model" in message.lower():
        assert row["status"] == "QUEUED" and not row.get("replay_of")
        assert not await jobs.read_events(new, 0)
    else:
        assert row["status"] == "COMPLETE" and row["replay_of"] == original


def test_pipeline_version_invalidates_previous_results():
    assert version.PIPELINE_VERSION == "0.2.1"
