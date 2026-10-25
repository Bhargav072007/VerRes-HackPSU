"""Contract-only job runner; provider failures become reviewable receipts."""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import monotonic

from pydantic import TypeAdapter

from api.app import version
from api.app.db import JobFailure
from api.app.providers.services import build_backend
from api.app.review import ReviewPanel, ReviewStub
from api.app.review.models import build_models
from api.app.review.runtime import ResilientGateway, job_context, provider_issues, stage_context
from api.app.verify.model import Model
from api.app.verify.outcomes import informational_citation
from contracts.interfaces import Review, Verify
from contracts.schema import (
    Citation,
    ClaimMap,
    ExistenceResult,
    HiddenTextFinding,
    Paper,
    Report,
    RetractionResult,
    ReviewSummary,
    SourceDocument,
    SupportResult,
)

logger = logging.getLogger(__name__)
DEADLINE_SECONDS = 300


class JobBusy(Exception):
    """Admission raced with another worker; keep the queued job scheduled."""


@dataclass
class Services:
    backend: object
    review: Review
    model_gateway: object = None
    backend_gateway: object = None
    model_unconfigured_reason: str | None = "model not configured"
    primary_model: Model | None = None
    adjudicator_model: Model | None = None
    adjudicator_unconfigured_reason: str | None = None

    async def aclose(self):
        try:
            await self.backend.__aexit__(None, None, None)
        finally:
            if self.model_gateway:
                await self.model_gateway.aclose()
            if (
                self.backend_gateway
                and getattr(self.backend, "gateway", None) is not self.backend_gateway
            ):
                await self.backend_gateway.aclose()


class UnconfiguredVerify(Verify):
    def __init__(self, reason: str):
        self.reason = reason

    async def verify_citation(self, citation: Citation, source: SourceDocument) -> SupportResult:
        return fallback("support", citation.id, self.reason)


def build_services(settings, pool=None, *, model: Model | None = None):
    model_gateway = None
    adjudicator = None
    gateway = None
    model_reason = "model not configured"
    adjudicator_reason = None
    if os.getenv("STUBS") == "1":
        from api.app.stubs import FixtureServices

        backend = FixtureServices()
        review = ReviewStub()
    else:
        from api.app.providers.cache import PostgresCache
        from api.app.providers.http import Policy, load_policies

        model_gateway, model, adjudicator, model_reason, adjudicator_reason = build_models(
            settings, pool, primary=model
        )
        if model is not None:
            logger.info(
                "model configured: %s/%s, adjudicator: %s/%s",
                model.vendor or model.family,
                model.model_id,
                (adjudicator.vendor or adjudicator.family) if adjudicator else "openai",
                adjudicator.model_id if adjudicator else "none",
            )
        else:
            logger.warning("model not configured: %s", model_reason)
        if adjudicator_reason and settings.model_adjudicator:
            logger.warning("adjudicator not configured: %s", adjudicator_reason)
        policies = load_policies()
        policies["grobid"] = Policy(settings.grobid_url, 1, 1, 1)
        policies["arxiv-intake"] = Policy("https://arxiv.org", 1, 3, 1)
        gateway = ResilientGateway(policies, cache=PostgresCache(pool) if pool else None)
        backend = build_backend(
            settings, pool=pool, gateway=gateway, primary=model, adjudicator=adjudicator
        )
        if model is None:
            backend.verify = UnconfiguredVerify(model_reason)
        review = ReviewPanel(model)
    return Services(
        backend,
        review,
        model_gateway,
        gateway,
        model_reason,
        primary_model=model if model_reason is None else None,
        adjudicator_model=adjudicator,
        adjudicator_unconfigured_reason=adjudicator_reason,
    )


def fallback(kind, row_id, reason):
    common = {"reason": reason}
    return {
        "existence": lambda: ExistenceResult(
            reference_id=row_id, status="CHECK_INCOMPLETE", **common
        ),
        "retraction": lambda: RetractionResult(reference_id=row_id, status="UNKNOWN", **common),
        "source": lambda: SourceDocument(
            reference_id=row_id, evidence_level="METADATA_ONLY", status="CHECK_INCOMPLETE", **common
        ),
        "support": lambda: SupportResult(
            citation_id=row_id,
            label="NEEDS_REVIEW",
            evidence_strength="INSUFFICIENT",
            needs_review_reason=reason,
            **common,
        ),
        "claim_map": lambda: ClaimMap(
            paper_id=row_id, status="NEEDS_REVIEW", needs_review_reason=reason
        ),
        "hidden_text": lambda: [
            HiddenTextFinding(id="scan-incomplete", kind="CHECK_INCOMPLETE", quote="", **common)
        ],
        "review_summary": lambda: ReviewSummary(warning=reason),
        "paper": lambda: Paper(id=row_id, status="NEEDS_REVIEW", needs_review_reason=reason),
    }[kind]()


class Pipeline:
    def __init__(self, bus, services, settings, *, deadline=DEADLINE_SECONDS):
        self.bus, self.services, self.settings = bus, services, settings
        self.deadline = deadline
        self.pending = set()
        self.stage_started = {}
        self.stage_durations = {}

    async def emit(self, kind, payload):
        result = await self.bus.emit(self.job_id, kind, payload.model_dump(mode="json"))
        if isinstance(result, JobFailure):
            if result.code == "rate_limited":
                raise JobBusy()
            raise RuntimeError("Could not persist pipeline event")

    async def stage(self, name, status, reason=None):
        from contracts.events import StagePayload

        await self.emit("stage", StagePayload(stage=name, status=status, reason=reason))
        if status == "STARTED":
            self.pending.add(name)
            self.stage_started[name] = monotonic()
        else:
            self.pending.discard(name)
            duration = monotonic() - self.stage_started.pop(name, monotonic())
            self.stage_durations[name] = self.stage_durations.get(name, 0) + duration
            logger.info(
                "stage finished",
                extra={
                    "job_id": str(self.job_id),
                    "stage": name,
                    "duration_seconds": round(duration, 6),
                },
            )

    async def call(self, name, kind, row_id, operation, result_type):
        await self.stage(name, "STARTED")
        reason = None
        issues = []
        issue_token = provider_issues.set(issues)
        stage_token = stage_context.set(name)
        try:
            result = await operation()
            items = result if isinstance(result, list) else [result]
            expected = HiddenTextFinding if kind == "hidden_text" else result_type
            if (kind != "hidden_text" and isinstance(result, list)) or not all(
                isinstance(item, expected) for item in items
            ):
                raise TypeError("Expected contract result")
            adapter = TypeAdapter(result_type)
            result = adapter.validate_python(adapter.dump_python(result, mode="json"))
            for item in items:
                identity = getattr(item, "reference_id", getattr(item, "citation_id", None))
                if identity is not None and identity != row_id:
                    raise ValueError("Result belongs to another row")
            if kind == "claim_map" and result.paper_id != row_id:
                raise ValueError("Map belongs to another paper")
            if kind == "paper" and not any(s.text.strip() for s in result.sentences):
                raise ValueError("Paper has no extracted text")
            if (
                kind == "source"
                and result.status == "AVAILABLE"
                and result.evidence_level != "METADATA_ONLY"
                and not any(p.text.strip() for p in result.passages)
            ):
                raise ValueError("Source has no evidence text")
            # An empty clean scan is valid; an interrupted one needs a receipt.
            if kind == "hidden_text" and not result and issues:
                raise ValueError("Hidden-text scan returned no result after provider issues")
        except Exception as error:
            reason = f"{name.split(':')[0]} failed ({type(error).__name__}); needs review"
            logger.warning(
                "stage failed job_id=%s ref_id=%s row_id=%s stage=%s error=%s",
                self.job_id,
                next(
                    (c.reference_id for c in self.report.paper.citations if c.id == row_id), row_id
                )
                if self.report.paper
                else row_id,
                row_id,
                name,
                type(error).__name__,
            )
            result = fallback(kind, row_id, reason)
        finally:
            provider_issues.reset(issue_token)
            stage_context.reset(stage_token)
        if issues:
            reason = "; ".join(dict.fromkeys(issues))
            logger.warning(
                "stage provider issues job_id=%s row_id=%s stage=%s: %s",
                self.job_id,
                row_id,
                name,
                reason,
            )
        await self.stage(name, "CHECK_INCOMPLETE" if reason else "COMPLETED", reason)
        return result

    async def row(self, kind, row_id, operation, result_type):
        result = await self.call(f"{kind}:{row_id}", kind, row_id, operation, result_type)
        await self.emit(kind, result)
        getattr(
            self.report, {"retraction": "retractions", "source": "sources"}.get(kind, kind)
        ).append(result)
        return result

    async def reference(self, reference):
        backend, paper = self.services.backend, self.report.paper
        existence = await self.row(
            "existence",
            reference.id,
            lambda: backend.resolve.resolve_reference(reference),
            ExistenceResult,
        )
        await self.row(
            "retraction",
            reference.id,
            lambda: backend.resolve.check_retraction(existence, (paper.paper_date) or date.today()),
            RetractionResult,
        )
        source = await self.row(
            "source", reference.id, lambda: backend.sources.fetch_source(existence), SourceDocument
        )
        await asyncio.gather(
            *(
                self.row(
                    "support",
                    citation.id,
                    lambda c=citation: backend.verify.verify_citation(c, source),
                    SupportResult,
                )
                for citation in paper.citations
                if citation.reference_id == reference.id
            )
        )

    async def scan(self, data):
        findings = await self.call(
            "hidden_text",
            "hidden_text",
            self.report.paper.id,
            lambda: self.services.backend.ingest.scan_hidden_text(data),
            list[HiddenTextFinding],
        )
        self.report.hidden_text = findings
        self.scanned = True
        for finding in findings:
            await self.emit("hidden_text", finding)

    async def graph(self):
        self.report.claim_map = await self.call(
            "build_claim_map",
            "claim_map",
            self.report.paper.id,
            lambda: self.services.backend.graph.build_claim_map(self.report.paper),
            ClaimMap,
        )

    async def flow(self, data):
        backend = self.services.backend
        self.report.paper = await self.call(
            "parse_pdf",
            "paper",
            f"paper-{self.job_id}",
            lambda: backend.ingest.parse_pdf(data),
            Paper,
        )
        paper = self.report.paper
        if paper.status == "NEEDS_REVIEW" and not paper.sentences:
            return paper.needs_review_reason or "PDF parsing failed"
        await self.emit("paper", paper)
        review = self.services.review
        if isinstance(review, ReviewPanel):
            review = ReviewPanel(
                review.model, report=self.report, on_review=lambda c: self.emit("review", c)
            )
        async with asyncio.TaskGroup() as tasks:
            scan = tasks.create_task(self.scan(data))
            graph = tasks.create_task(self.graph())
            prep = tasks.create_task(
                self.call(
                    "review_prep",
                    "review_summary",
                    paper.id,
                    lambda: review.prepare(paper),
                    ReviewSummary,
                )
            )
            await asyncio.gather(*(self.reference(reference) for reference in paper.references))
            await self.fill_rows("Citation reference is missing")
            await prep
            await scan
            self.report.review = await self.call(
                "run_review_panel",
                "review_summary",
                paper.id,
                lambda: review.run_review_panel(paper, self.report.support),
                ReviewSummary,
            )
            if not isinstance(review, ReviewPanel):
                for comment in self.report.review.comments:
                    await self.emit("review", comment)
            await self.emit("review_summary", self.report.review)
            await graph
            await self.stage("claim_map", "STARTED")
            await self.emit("claim_map", self.report.claim_map)
            await self.stage("claim_map", "COMPLETED")
        return None

    async def fill_rows(self, reason):
        paper = self.report.paper
        for kind, field, id_field, rows in (
            ("existence", "existence", "reference_id", paper.references),
            ("retraction", "retractions", "reference_id", paper.references),
            ("source", "sources", "reference_id", paper.references),
            ("support", "support", "citation_id", paper.citations),
        ):
            completed = {getattr(result, id_field) for result in getattr(self.report, field)}
            for row in rows:
                if row.id not in completed:
                    name = f"{kind}:{row.id}"
                    if name not in self.pending:
                        await self.stage(name, "STARTED")
                    result = fallback(kind, row.id, reason)
                    await self.emit(kind, result)
                    await self.stage(name, "CHECK_INCOMPLETE", reason)
                    getattr(self.report, field).append(result)

    async def run_job(self, job_id):
        token = job_context.set(str(job_id))
        try:
            await self._run_job(job_id)
        finally:
            job_context.reset(token)

    async def _run_job(self, job_id):
        from api.app.routes.jobs import load_pdf

        self.job_id = job_id
        self.report = Report(
            job_id=job_id,
            status="COMPLETE",
            pipeline_version=version.PIPELINE_VERSION,
            git_sha=version.GIT_SHA,
            started_at=datetime.now(UTC),
        )
        self.scanned = False
        reason = None
        try:
            async with asyncio.timeout(self.deadline):
                row = await self.bus.jobs.get(job_id)
                if row is None or row["status"] not in ("QUEUED", "RUNNING"):
                    return
                if row.get("demo_fixture"):
                    from api.app.routes.demo import replay_recording

                    await replay_recording(self.bus, job_id, row["input"])
                    return
                await self.stage("intake", "STARTED")
                job_input = row["input"]
                if isinstance(job_input, str):
                    job_input = json.loads(job_input)
                data = await load_pdf(
                    job_input,
                    self.settings,
                    gateway=getattr(self.services.backend, "gateway", None),
                )
                reason = data.message if isinstance(data, JobFailure) else None
                if not reason:
                    self.report.pdf_sha256 = hashlib.sha256(data).hexdigest()
                await self.stage("intake", "CHECK_INCOMPLETE" if reason else "COMPLETED", reason)
                if not reason:
                    reason = await self.flow(data)
        except TimeoutError:
            reason = "timed out"
            if self.report.paper is not None:
                await self.fill_rows(reason)
                if not self.scanned:
                    self.report.hidden_text = fallback("hidden_text", "", reason)
                    for finding in self.report.hidden_text:
                        await self.emit("hidden_text", finding)
                if self.report.review is None:
                    self.report.review = fallback("review_summary", "", reason)
                    await self.emit("review_summary", self.report.review)
                if self.report.claim_map is None:
                    self.report.claim_map = fallback("claim_map", self.report.paper.id, reason)
                await self.emit("claim_map", self.report.claim_map)
        for stage in sorted(self.pending):
            await self.stage(stage, "CHECK_INCOMPLETE", reason or "Stage interrupted")
        await self.stage("summary", "STARTED")
        if reason:
            from contracts.events import ErrorPayload

            await self.emit("error", ErrorPayload(code="CHECK_INCOMPLETE", reason=reason))
            self.report.status, self.report.reason = "CHECK_INCOMPLETE", reason
        elif (
            self.report.paper.status == "NEEDS_REVIEW"
            or any(
                r.status not in ("VERIFIED", "VERIFIED_WITH_DISCREPANCIES")
                for r in self.report.existence
            )
            or any(r.status != "NONE" for r in self.report.retractions)
            or any(r.status == "CHECK_INCOMPLETE" for r in self.report.sources)
            or any(
                r.label != "SUPPORTED" and not informational_citation(r)
                for r in self.report.support
            )
            or self.report.hidden_text
            or self.report.claim_map.status == "NEEDS_REVIEW"
            or self.report.review.warning
        ):
            self.report.status = "NEEDS_REVIEW"
        await self.stage("summary", "COMPLETED")
        self.report.finished_at = datetime.now(UTC)
        self.report.stage_durations = self.stage_durations
        await self.emit("done", self.report)


class Runner:
    def __init__(self, bus, services, settings, tasks):
        self.bus, self.services, self.settings, self.tasks = bus, services, settings, tasks
        self.active = {}
        # Leave pool connections available for event transactions while leases are held.
        self.slots = asyncio.Semaphore(3)

    def start(self, job_id):
        if job_id not in self.active:
            task = asyncio.create_task(self.run_job(job_id))
            self.active[job_id] = task
            self.tasks.add(task)
            task.add_done_callback(lambda done: self.finished(job_id, done))
        return self.active[job_id]

    async def run_job(self, job_id):
        async with self.slots, self.bus.jobs.lease(job_id) as locked:
            if locked:
                while True:
                    try:
                        await Pipeline(self.bus, self.services, self.settings).run_job(job_id)
                        return
                    except JobBusy:
                        await asyncio.sleep(0.25)

    def finished(self, job_id, task):
        self.active.pop(job_id, None)
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "job interrupted job_id=%s error=%s",
                job_id,
                type(task.exception()).__name__,
                extra={"job_id": str(job_id), "stage": "runner"},
            )

    async def recover(self):
        for row in await self.bus.jobs.unfinished():
            self.start(row["id"])
