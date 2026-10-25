"""Exercise the real frozen interfaces, persisted contracts, and A2 SSE payloads."""

import inspect
import json
from copy import deepcopy
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from pydantic import TypeAdapter

from api.app.graph.service import GraphService, validate_claim_map
from api.app.ingest.service import IngestService
from api.app.providers.cache import PostgresCache
from api.app.providers.http import Gateway, Policy, load_policies
from api.app.providers.metadata import Crossref, OpenAlex
from api.app.providers.models import ProviderResult, Work
from api.app.providers.services import build_backend
from api.app.resolve.retraction import PostgresRetractions, RetractionRecord
from api.app.resolve.service import ResolveService
from api.app.settings import Settings
from api.app.sources.service import SourceService
from api.app.verify.model import strict_schema
from api.app.verify.service import VerifyService
from api.tests.helpers import FixtureModel, judgment
from contracts import interfaces
from contracts.events import (
    ClaimMapEvent,
    DoneEvent,
    ExistenceEvent,
    HiddenTextEvent,
    PaperEvent,
    RetractionEvent,
    SourceEvent,
    SSEEvent,
    SupportEvent,
)
from contracts.schema import (
    Citation,
    ClaimEdge,
    ClaimMap,
    ClaimNode,
    EvidenceLevel,
    ExistenceResult,
    ExistenceStatus,
    Judgment,
    Paper,
    Reference,
    Report,
    RetractionResult,
    RetractionStatus,
    Sentence,
    SourceDocument,
    SourcePassage,
    SupportLabel,
    SupportResult,
)


def provider(name, works, *, definitive=True):
    result = ProviderResult(provider=name, definitive=definitive, works=works)
    return type(
        "Provider",
        (),
        {"lookup": AsyncMock(return_value=result), "search": AsyncMock(return_value=result)},
    )()


def citation_source(text, level=EvidenceLevel.FULL_TEXT, passage_id="external-passage-42"):
    citation = Citation(id="c1", reference_id="b1", sentence_ids=["s1"], claim_text=text)
    source = SourceDocument(
        reference_id="b1",
        evidence_level=level,
        passages=[SourcePassage(passage_id=passage_id, text=text)],
        reason="explicit deterministic fixture",
    )
    return citation, source


async def test_all_public_interface_signatures_and_resource_ownership():
    async with build_backend(Settings(_env_file=None, crossref_mailto=None)) as services:
        for service, protocol, names in (
            (services.ingest, interfaces.Ingest, {"parse_pdf", "scan_hidden_text"}),
            (services.resolve, interfaces.Resolve, {"resolve_reference", "check_retraction"}),
            (services.sources, interfaces.Sources, {"fetch_source"}),
            (services.verify, interfaces.Verify, {"verify_citation"}),
            (services.graph, interfaces.Graph, {"build_claim_map"}),
        ):
            assert protocol in type(service).__mro__
            for name in names:
                method = getattr(service, name)
                assert inspect.iscoroutinefunction(method)
                expected = list(inspect.signature(getattr(protocol, name)).parameters)[1:]
                assert list(inspect.signature(method).parameters) == expected
        assert "grobid" in services.gateway.policies
        missing = await services.resolve.crossref.lookup("10.1234/fixture")
        assert not missing.definitive and "mailto" in missing.reason
    assert all(client.is_closed for client in services.gateway.clients.values())


async def test_ingest_returns_shared_paper_and_hidden_findings(tei, pdf_bytes):
    policies = load_policies()
    policies["grobid"] = Policy("http://grobid:8070", 100, 1, 1)
    async with Gateway(
        policies, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=tei))
    ) as gateway:
        service = IngestService(gateway)
        data = pdf_bytes()
        paper = await service.parse_pdf(data)
        assert isinstance(paper, Paper) and paper.status == "PARSED"
        assert Paper.model_validate_json(paper.model_dump_json()) == paper
        assert len(paper.citations) == 1
        assert paper.citations[0].sentence_ids == ["s00003"]
        assert "Marked reference b1" in paper.citations[0].context
        assert paper.references[0].raw_text and paper.references[0].arxiv_id
        assert (await service.parse_pdf(data)).id == paper.id
        findings = await service.scan_hidden_text(pdf_bytes(hidden=True))
        assert {finding.kind for finding in findings} == {"HIDDEN_TEXT"}
        assert any("INSTRUCTION_PATTERN" in finding.reason for finding in findings)
        assert (await service.parse_pdf(b"broken")).status == "NEEDS_REVIEW"
        assert (await service.scan_hidden_text(b"broken"))[0].kind == "CHECK_INCOMPLETE"


async def test_public_resolution_and_conservative_unknown_index_type():
    reference = Reference(
        id="b1",
        raw_text="Smith: An extended real scientific study title",
        title="An extended real scientific study title",
        authors=["Smith"],
        year=2024,
        doi="10.1234/a",
    )
    work = Work(
        provider="crossref",
        id=reference.doi,
        title=reference.title,
        authors=reference.authors,
        year=2024,
        doi=reference.doi,
    )
    service = ResolveService(provider("crossref", [work]), provider("openalex", []))
    found = await service.resolve_reference(reference)
    assert isinstance(found, ExistenceResult) and found.status == ExistenceStatus.VERIFIED
    assert found.reference_id == found.matched_reference.id == reference.id
    assert found.provider_ids["doi"] == reference.doi and found.receipt_urls
    service = ResolveService(provider("crossref", []), provider("openalex", []))
    checked = await service.resolve_reference(reference.model_copy(update={"doi": None}))
    assert checked.status == ExistenceStatus.CHECK_INCOMPLETE
    # A1 does not carry work type. A DOI/long title alone cannot prove index coverage.
    assert "coverage" in checked.reason


async def test_public_retraction_uses_frozen_statuses_and_dates():
    reference = Reference(
        id="b1",
        raw_text="Paper",
        title="A real study title",
        authors=["Smith"],
        year=2024,
        doi="10.1234/a",
    )
    existence = ExistenceResult(
        reference_id="b1", status="VERIFIED", matched_reference=reference, reason="metadata agree"
    )
    work = Work(
        provider="openalex",
        id="W1",
        doi=reference.doi,
        title=reference.title,
        authors=reference.authors,
        year=2024,
        is_retracted=True,
    )
    records = [
        RetractionRecord(
            doi=reference.doi,
            retracted=date(2023, 1, 1),
            provenance="fixture",
            notice_url="https://doi.org/10.1234/notice",
        )
    ]
    store = type("Store", (), {"lookup": AsyncMock(return_value=records)})()
    service = ResolveService(None, provider("openalex", [work]), retractions=store)
    result = await service.check_retraction(existence, date(2024, 1, 1))
    assert isinstance(result, RetractionResult) and result.status == RetractionStatus.RETRACTED
    assert result.checked_as_of
    assert result.notice_urls == ["https://doi.org/10.1234/notice"]
    assert (await service.check_retraction(existence, None)).status == RetractionStatus.UNKNOWN


@pytest.mark.parametrize("level", [EvidenceLevel.ABSTRACT_ONLY, EvidenceLevel.FULL_TEXT])
async def test_verification_preserves_shared_passage_ids(claim, level):
    citation, source = citation_source(claim.text, level)
    primary = FixtureModel(
        {
            "classify": {"items": [{"citation_id": "c1", "function": "SPECIFIC_CLAIM"}]},
            "split": {"ambiguous": False, "claims": [claim.model_dump()]},
            "judge": judgment(passage_id="external-passage-42").model_dump(),
        }
    )
    result = await VerifyService(primary).verify_citation(citation, source)
    assert isinstance(result, SupportResult) and result.label == SupportLabel.SUPPORTED
    assert result.evidence[0].passage_id == source.passages[0].passage_id
    assert result.evidence_strength == "DIRECT" and not result.adjudicated
    assert result.model_id == primary.model_id and result.prompt_version == "v3"
    assert f"vendor={primary.vendor}, family={primary.family}" in result.reason
    sent_schema = primary.calls[-1]["schema"]
    assert sent_schema["properties"]["evidence"].pop("maxItems") == 3
    assert sent_schema == Judgment.model_json_schema()


async def test_public_severe_finding_requires_independent_same_receipts(claim):
    citation, source = citation_source(claim.text)
    answer = judgment("CONTRADICTED", passage_id="external-passage-42").model_dump()
    primary = FixtureModel(
        {
            "classify": {"items": [{"citation_id": "c1", "function": "SPECIFIC_CLAIM"}]},
            "split": {"ambiguous": False, "claims": [claim.model_dump()]},
            "judge": answer,
        }
    )
    second = FixtureModel({"adjudicate": answer}, model_id="other", family="other-family")
    result = await VerifyService(primary, adjudicator=second).verify_citation(citation, source)
    assert result.label == SupportLabel.CONTRADICTED and result.adjudicated
    assert result.model_id == f"{primary.model_id}, {second.model_id}"
    assert f"vendor={second.vendor}, family={second.family}" in result.reason
    assert "same vendor" not in result.reason
    assert all(e.passage_id == "external-passage-42" for e in result.evidence)
    source.evidence_level = EvidenceLevel.ABSTRACT_ONLY
    result = await VerifyService(primary, adjudicator=second).verify_citation(citation, source)
    assert result.label == SupportLabel.NEEDS_REVIEW and result.needs_review_reason


async def test_unconfigured_or_misaligned_verification_is_explicit(claim):
    citation, source = citation_source(claim.text)
    result = await VerifyService().verify_citation(citation, source)
    assert result.label == SupportLabel.NEEDS_REVIEW and result.evidence_strength == "INSUFFICIENT"
    source.reference_id = "wrong"
    assert "different reference" in (await VerifyService().verify_citation(citation, source)).reason


def test_shared_judgment_rendering_does_not_mutate_contract_schema():
    schema = Judgment.model_json_schema()
    before = deepcopy(schema)
    strict = strict_schema(schema)
    assert schema == before
    assert set(strict["required"]) == set(strict["properties"])
    assert strict["additionalProperties"] is False


async def test_claim_map_shared_schema_and_validation():
    paper = Paper(id="p", sentences=[Sentence(id="s1", text="A result", section="Results")])
    proposal = ClaimMap(
        paper_id="p", nodes=[ClaimNode(id="n1", text="A result", sentence_ids=["s1"])]
    )
    model = FixtureModel({"claim_map": proposal.model_dump()})
    actual = await GraphService(model).build_claim_map(paper)
    assert isinstance(actual, ClaimMap) and actual == proposal
    assert model.calls[0]["schema"] == ClaimMap.model_json_schema()
    bad = proposal.model_copy(
        update={
            "nodes": proposal.nodes
            + [ClaimNode(id="n2", text="Invented", sentence_ids=["missing"])],
            "edges": [
                ClaimEdge(source_id="n1", target_id="n1", relation="DEPENDS_ON", reason="cycle")
            ],
        }
    )
    checked = validate_claim_map(bad, paper)
    assert len(checked.nodes) == 1 and not checked.edges and checked.status == "NEEDS_REVIEW"


async def test_jsonb_cache_matches_a1_schema():
    class Pool:
        def __init__(self):
            self.payload = None

        async def execute(self, sql, key, payload, ttl):
            assert "cache_key,payload,expires_at" in sql and "::jsonb" in sql
            self.payload = payload

        async def fetchrow(self, sql, key):
            assert sql.startswith("SELECT payload FROM http_cache")
            return {"payload": self.payload}

    from api.app.providers.models import HTTPResult

    pool = Pool()
    cache = PostgresCache(pool)
    await cache.put("k", HTTPResult(status=200, content=b"\xffbinary", headers={"x": "y"}), 10)
    assert (await cache.get("k")).content == b"\xffbinary"
    pool.payload = '{"invalid":"legacy cache entry"}'
    assert await cache.get("k") is None


async def test_retraction_import_and_lookup_use_existing_jsonb_table():
    class Pool:
        def __init__(self):
            self.rows = []
            self.snapshot = None

        def acquire(self):
            return self

        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def executemany(self, sql, rows):
            assert "retraction_watch(doi,payload)" in sql and "updated_at=now()" in sql
            self.rows = rows

        async def execute(self, sql, *args):
            if sql.startswith("INSERT INTO http_cache"):
                self.snapshot = json.loads(args[1])

        async def fetchrow(self, sql, key, doi):
            assert "payload AS snapshot" in sql and key == PostgresRetractions.SNAPSHOT_KEY
            return {
                "snapshot": self.snapshot,
                "records": [json.loads(payload) for key, payload in self.rows if key == doi],
            }

    adapter = PostgresRetractions(Pool())
    assert await adapter.import_csv(
        "OriginalPaperDOI,RetractionDate\n10.1234/a,2023-01-01\n",
        complete=True,
        fetched_at=datetime.now(UTC),
    ) == (
        1,
        0,
    )
    assert (await adapter.lookup("10.1234/a"))[0].retracted == date(2023, 1, 1)


async def test_entire_shared_pipeline_round_trips_as_a2_report(tei, pdf_bytes, claim):
    crossref_payload = {
        "message": {
            "DOI": "10.1234/animal.1",
            "title": ["Controlled animal intervention study"],
            "author": [{"family": "Smith"}],
            "published": {"date-parts": [[2024]]},
        }
    }
    openalex_payload = {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.1234/animal.1",
        "title": "Controlled animal intervention study",
        "publication_year": 2024,
        "authorships": [{"author": {"display_name": "Jane Smith"}}],
        "best_oa_location": {"pdf_url": "https://papers.example/source.pdf"},
        "meta": {"cost_usd": 0},
        "is_retracted": False,
    }

    def handler(request):
        if request.url.host == "grobid":
            return httpx.Response(200, content=tei)
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=crossref_payload)
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json=openalex_payload)
        return httpx.Response(200, content=pdf_bytes())

    async def dns(host, port):
        return ["93.184.216.34"]

    policies = load_policies()
    policies["grobid"] = Policy("http://grobid:8070", 100, 1, 1)
    async with Gateway(policies, transport=httpx.MockTransport(handler), resolver=dns) as gateway:
        paper = await IngestService(gateway).parse_pdf(pdf_bytes())
        crossref, openalex = Crossref(gateway, "r@example.org"), OpenAlex(gateway)
        resolver = ResolveService(crossref, openalex)
        existence = await resolver.resolve_reference(paper.references[0])
        source = await SourceService(gateway, crossref=crossref, openalex=openalex).fetch_source(
            existence
        )
        assert source.evidence_level == EvidenceLevel.FULL_TEXT
        claim.magnitude = None
        model = FixtureModel(
            {
                "classify": {"items": [{"citation_id": "c00001", "function": "SPECIFIC_CLAIM"}]},
                "split": {"ambiguous": False, "claims": [claim.model_dump()]},
                "judge": judgment().model_dump(),
            }
        )
        support = await VerifyService(model).verify_citation(paper.citations[0], source)
        retraction = await resolver.check_retraction(existence, paper.paper_date)
        graph = await GraphService().build_claim_map(paper)
        hidden = await IngestService(gateway).scan_hidden_text(b"invalid")
    assert support.label == SupportLabel.SUPPORTED
    report = Report(
        job_id=uuid4(),
        paper=paper,
        existence=[existence],
        sources=[source],
        support=[support],
        retractions=[retraction],
        claim_map=graph,
        hidden_text=hidden,
        status="NEEDS_REVIEW",
        reason="RW/model graph not configured",
    )
    assert Report.model_validate_json(report.model_dump_json()) == report
    for seq, event in enumerate(
        (
            PaperEvent,
            ExistenceEvent,
            SourceEvent,
            SupportEvent,
            RetractionEvent,
            ClaimMapEvent,
            HiddenTextEvent,
            DoneEvent,
        ),
        1,
    ):
        payload = (paper, existence, source, support, retraction, graph, hidden[0], report)[seq - 1]
        message = event(job_id=report.job_id, seq=seq, payload=payload)
        assert TypeAdapter(SSEEvent).validate_json(message.model_dump_json()) == message
