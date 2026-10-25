"""Real exported identities; OpenAlex flags/IDs below are synthetic transport responses."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from api.app.providers.http import Gateway
from api.app.providers.metadata import OpenAlex
from api.app.providers.models import Work
from api.app.resolve.retraction import RetractionRecord
from api.app.resolve.service import ResolveService
from api.tests.test_shared_interfaces import provider
from contracts.schema import ExistenceResult

ROWS = [
    json.loads(line)
    for line in (Path(__file__).parent / "fixtures/paper3-doiless-retractions.jsonl")
    .read_text()
    .splitlines()
]
TODAY = date(2026, 10, 25)


@pytest.fixture
def existence():
    return ExistenceResult.model_validate(ROWS[0]["existence"])


@pytest.fixture
def work(existence):
    ref = existence.matched_reference
    return Work(
        provider="openalex",
        id="https://openalex.org/W1",
        title=ref.title,
        authors=ref.authors,
        year=ref.year,
        is_retracted=False,
    )


@pytest.mark.parametrize("row", ROWS, ids=["attention", "bert", "resnet"])
async def test_exported_doiless_identities_get_openalex_receipts(row):
    existence = ExistenceResult.model_validate(row["existence"])
    ref = existence.matched_reference
    assert row["synthetic_paper"] is True and ref.doi is None
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "title": ref.title,
                        "publication_year": ref.year,
                        "is_retracted": False,
                        "authorships": [{"author": {"display_name": name}} for name in ref.authors],
                    }
                ]
            },
        )

    async with Gateway(transport=httpx.MockTransport(handler), attempts=1) as gateway:
        result = await ResolveService(None, OpenAlex(gateway)).check_retraction(existence, TODAY)
    assert result.status == "NONE" and result.reason == "No retraction found (OpenAlex)"
    assert result.source_url == "https://openalex.org/W1" and result.source_type == "openalex"
    assert result.checked_as_of and result.notice_urls == []
    assert len(requests) == 1 and requests[0].url.params["search"] == ref.title


@pytest.mark.parametrize("flag,status", [(False, "NONE"), (True, "RETRACTED"), (None, "UNKNOWN")])
@pytest.mark.parametrize("doi", [None, "10.1234/a"])
async def test_flags_with_or_without_doi_during_notice_provider_outages(
    existence, work, flag, status, doi
):
    existence.matched_reference.doi = doi
    work.doi, work.is_retracted = doi, flag
    watch = type("Watch", (), {"lookup": AsyncMock(return_value=None)})()
    service = ResolveService(
        provider("crossref", [], definitive=False), provider("openalex", [work]), retractions=watch
    )
    result = await service.check_retraction(existence, TODAY)
    assert result.status == status
    if flag is not None:
        assert result.source_url == work.id and result.source_type == "openalex"
        assert result.reason == (
            "Marked retracted by OpenAlex; notice date unavailable"
            if flag
            else "No retraction found (OpenAlex)"
        )
    if doi:
        watch.lookup.assert_awaited_once_with(doi)


@pytest.mark.parametrize(
    "kind,status",
    [
        ("RETRACTION", "RETRACTED"),
        ("CORRECTION", "CORRECTED"),
        ("EXPRESSION_OF_CONCERN", "EXPRESSION_OF_CONCERN"),
    ],
)
async def test_notices_on_an_openalex_discovered_doi_override_false(existence, work, kind, status):
    work.doi = "10.1234/discovered"
    record = RetractionRecord(
        doi=work.doi,
        retracted=date(2020, 1, 1),
        notice_type=kind,
        notice_url="https://doi.org/10.1234/notice",
        provenance="Retraction Watch fixture",
    )
    watch = type("Watch", (), {"lookup": AsyncMock(return_value=[record])})()
    service = ResolveService(None, provider("openalex", [work]), retractions=watch)
    result = await service.check_retraction(existence, TODAY)
    assert result.status == status and result.source_type == "retraction_watch"
    assert result.source_url == record.notice_url and result.notice_urls == [record.notice_url]
    watch.lookup.assert_awaited_once_with(work.doi)
    assert (await service.check_retraction(existence, date(2019, 1, 1))).status == "NONE"


async def test_undated_notice_cannot_be_erased_by_false_flag(existence, work):
    existence.matched_reference.doi = work.doi = "10.1234/a"
    record = RetractionRecord(
        doi=work.doi, retracted=None, notice_url="https://doi.org/10.1234/n", provenance="fixture"
    )
    watch = type("Watch", (), {"lookup": AsyncMock(return_value=[record])})()
    result = await ResolveService(
        None, provider("openalex", [work]), retractions=watch
    ).check_retraction(existence, TODAY)
    assert result.status == "UNKNOWN" and result.notice_urls == [record.notice_url]


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "A different paper"},
        {"authors": ["Different Author"]},
        {"year": 2001},
        {"id": "https://untrusted.example/W1"},
    ],
)
async def test_mismatched_metadata_never_authorizes_a_flag(existence, work, changes):
    result = await ResolveService(
        None, provider("openalex", [work.model_copy(update=changes)])
    ).check_retraction(existence, TODAY)
    assert result.status == "UNKNOWN" and result.source_url is None


async def test_ambiguous_or_failed_lookups_remain_unknown(existence, work):
    for works, definitive in [
        ([work, work.model_copy(update={"id": "W2"})], True),
        ([work], False),
        ([], True),
    ]:
        result = await ResolveService(
            None, provider("openalex", works, definitive=definitive)
        ).check_retraction(existence, TODAY)
        assert result.status == "UNKNOWN"


async def test_provider_id_is_reused_and_checked(existence, work):
    existence.provider_ids["openalex"] = "W1"
    alex = provider("openalex", [work])
    service = ResolveService(None, alex)
    assert (await service.check_retraction(existence, TODAY)).status == "NONE"
    alex.lookup.assert_awaited_once_with("W1")
    alex.search.assert_not_called()
    work.id = "W2"
    assert (await service.check_retraction(existence, TODAY)).status == "UNKNOWN"


async def test_unverified_identity_or_missing_citing_date_stays_unknown(existence, work):
    alex = provider("openalex", [work])
    service = ResolveService(None, alex)
    assert (await service.check_retraction(existence, None)).status == "UNKNOWN"
    for status in ["AMBIGUOUS", "NOT_FOUND", "DOI_MISMATCH"]:
        existence.status = status
        alex.search.reset_mock()
        alex.lookup.reset_mock()
        assert (await service.check_retraction(existence, TODAY)).status == "UNKNOWN"
        alex.search.assert_not_called()
        alex.lookup.assert_not_called()


@pytest.mark.parametrize("identifier", ["1706.03762v7", "arXiv:1706.03762v7"])
@pytest.mark.parametrize("returned", [None, "1706.03762v1"])
async def test_arxiv_doi_disambiguates_search_copies(existence, work, identifier, returned):
    existence.matched_reference.arxiv_id = identifier
    work.arxiv = returned
    work.doi = "10.48550/arxiv.1706.03762"
    other = work.model_copy(
        update={"id": "W2", "doi": "10.1234/other", "arxiv": None, "is_retracted": True}
    )
    service = ResolveService(None, provider("openalex", [work, other]))
    assert (await service.check_retraction(existence, TODAY)).status == "NONE"
