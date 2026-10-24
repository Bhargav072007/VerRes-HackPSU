from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
from app.ingest.models import Reference
from app.ingest.tei import identifiers
from app.providers.http import Circuit, Gateway
from app.providers.models import ProviderResult, Work
from app.resolve.doi import check_doi
from app.resolve.existence import combine_works
from app.resolve.retraction import PostgresRetractions, read_watch_csv
from app.sources.acquire import acquire_source
from app.verify.pipeline import classify_citations
from conftest import FixtureModel


def test_interleaved_success_does_not_erase_throttle_window():
    circuit = Circuit()
    for stamp in (0, 10, 20):
        circuit.record(False, 200, stamp)
        circuit.record(True, 429, stamp + 1)
    assert not circuit.enter(22)


def test_doi_balanced_parentheses_are_preserved():
    assert identifiers("10.1234/paper(2024)")["doi"] == "10.1234/paper(2024)"
    assert identifiers("(10.1234/paper(2024)).")["doi"] == "10.1234/paper(2024)"


def test_corrections_are_not_imported_as_retractions():
    rows, rejected = read_watch_csv(
        "OriginalPaperDOI,RetractionDate,RetractionNature\n10.1234/a,2023-01-01,Correction\n10.1234/b,2023-01-01,Retraction\n"
    )
    assert len(rows) == 1 and rows[0].doi == "10.1234/b" and rejected == 1
    assert rows[0].retracted == date(2023, 1, 1)


def test_malformed_watch_header_is_not_a_successful_empty_import():
    assert read_watch_csv("wrong,columns\nsome,data") == ([], 1)


async def test_retraction_database_outage_returns_unknown():
    class Pool:
        async def fetch(self, *args):
            raise OSError("database unavailable")

    assert await PostgresRetractions(Pool()).lookup("10.1234/a") is None


@pytest.mark.parametrize(
    "case, expected",
    [
        ("missing", "CHECK_INCOMPLETE"),
        ("invalid", "INVALID"),
        ("notfound", "UNRESOLVED"),
        ("outage", "CHECK_INCOMPLETE"),
        ("mismatch", "DOI_MISMATCH"),
        ("match", "MATCH"),
        ("disagree", "AMBIGUOUS"),
    ],
)
async def test_doi_failure_states(case, expected):
    ref = Reference(
        id="b1",
        raw="test",
        title="A real title",
        authors=["Smith"],
        year=2024,
        doi=None if case == "missing" else "invalid" if case == "invalid" else "10.1234/a",
    )
    work = Work(provider="crossref", id="a", title=ref.title, authors=ref.authors, year=ref.year)
    works = [] if case in {"notfound", "outage"} else [work]
    if case == "mismatch":
        work.title = "Something completely unrelated"
    other = (
        work.model_copy(update={"title": "Something completely unrelated"})
        if case == "disagree"
        else work
    )
    first = ProviderResult(provider="crossref", definitive=case != "outage", works=works)
    second = ProviderResult(
        provider="openalex", definitive=case != "outage", works=[other] if works else []
    )
    a = type("Provider", (), {"lookup": AsyncMock(return_value=first)})()
    b = type("Provider", (), {"lookup": AsyncMock(return_value=second)})()
    assert (await check_doi(ref, a, b)).status == expected


def test_combined_metadata_preserves_abstract_provenance():
    crossref = Work(provider="crossref", id="a", abstract="<p>An actual abstract.</p>")
    openalex = Work(provider="openalex", id="b", oa_url="https://example.org/paper")
    merged = combine_works([crossref, openalex])
    assert merged.oa_url and merged.abstract_origin == "crossref"
    assert merged.abstract == crossref.abstract


async def test_arxiv_pdf_uses_arxiv_limiter():
    async def dns(host, port):
        return ["93.184.216.34"]

    async with Gateway(
        resolver=dns, transport=httpx.MockTransport(lambda r: httpx.Response(404))
    ) as gateway:
        await gateway.safe_fetch("https://arxiv.org/pdf/2401.12345")
        assert gateway.limiters["arxiv"]._level > 0
        assert gateway.limiters["source"]._level == 0


async def test_crossref_abstract_has_priority_over_openalex_index():
    work = Work(
        provider="openalex", id="a", doi="10.1234/a", abstract_inverted_index={"Fallback": [0]}
    )
    crossref = Work(
        provider="crossref", id="b", doi="10.1234/a", abstract="<p>Preferred abstract.</p>"
    )
    async with Gateway() as gateway:
        source = await acquire_source(work, gateway, crossref_work=crossref)
    assert source.text == "Preferred abstract." and source.origin == "crossref"


async def test_unrelated_crossref_abstract_is_not_used():
    work = Work(
        provider="openalex", id="a", doi="10.1234/a", abstract_inverted_index={"Fallback": [0]}
    )
    unrelated = Work(provider="crossref", id="b", doi="10.1234/b", abstract="<p>Wrong source.</p>")
    async with Gateway() as gateway:
        source = await acquire_source(work, gateway, crossref_work=unrelated)
    assert source.text == "Fallback" and "Wrong" not in source.text


async def test_cached_openalex_records_remain_usable_after_budget_limit():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"meta": {"cost_usd": 1}, "results": []})

    async with Gateway(daily_budget_usd=1, transport=httpx.MockTransport(handler)) as gateway:
        await gateway.request("openalex", "/works", ttl=86400)
        assert (await gateway.request("openalex", "/works", ttl=86400)).cached
        assert (await gateway.request("openalex", "/other", ttl=86400)).error
    assert len(calls) == 1


async def test_classifier_batches_ten(citation):
    citations = [citation.model_copy(update={"id": f"c{i}"}) for i in range(21)]

    def classify(request):
        import html
        import json

        value = request["data"]
        raw = html.unescape(value[value.index(">") + 1 : value.rindex("<")])
        return json.dumps(
            {
                "items": [
                    {"citation_id": c["id"], "function": "SPECIFIC_CLAIM"} for c in json.loads(raw)
                ]
            }
        )

    model = FixtureModel({"classify": classify})
    assert len(await classify_citations(citations, model)) == 21
    assert len(model.calls) == 3
