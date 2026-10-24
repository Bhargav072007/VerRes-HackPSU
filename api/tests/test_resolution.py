from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from api.app.ingest.models import ParsedReference
from api.app.providers.http import DAY, Gateway
from api.app.providers.metadata import Arxiv, Crossref, OpenAlex
from api.app.providers.models import ProviderResult, Work
from api.app.resolve.existence import resolve_reference, score
from api.app.resolve.retraction import RetractionRecord, check_retraction, read_watch_csv


@pytest.fixture
def reference():
    return ParsedReference(
        id="b1",
        raw="Smith 2024 A controlled study of animal inflammation.",
        title="A controlled study of animal inflammation",
        authors=["Smith"],
        year=2024,
        venue="Animal Research",
        doi="10.1234/animal.1",
        kind="journal-article",
    )


@pytest.fixture
def work(reference):
    return Work(
        provider="crossref",
        id=reference.doi,
        doi=reference.doi,
        title=reference.title,
        authors=reference.authors,
        year=reference.year,
        venue=reference.venue,
        is_retracted=False,
    )


def provider(name, works, *, definitive=True):
    result = ProviderResult(provider=name, works=works, definitive=definitive)
    return type(
        "Provider",
        (),
        {"lookup": AsyncMock(return_value=result), "search": AsyncMock(return_value=result)},
    )()


async def test_identifier_match_and_metadata_agreement(reference, work):
    result = await resolve_reference(
        reference, provider("crossref", [work]), provider("openalex", [work])
    )
    assert result.status == "FOUND" and result.work == work


@pytest.mark.parametrize(
    "changes",
    [{"title": "A completely different unrelated work"}, {"authors": ["Jones"]}, {"year": 2000}],
)
async def test_wrong_doi_metadata(reference, work, changes):
    wrong = work.model_copy(update=changes)
    result = await resolve_reference(
        reference, provider("crossref", [wrong]), provider("openalex", [wrong])
    )
    assert result.status == "DOI_MISMATCH"


async def test_identifier_provider_disagreement(reference, work):
    wrong = work.model_copy(update={"title": "A completely different unrelated work"})
    result = await resolve_reference(
        reference, provider("crossref", [work]), provider("openalex", [wrong])
    )
    assert result.status == "AMBIGUOUS"


async def test_search_duplicate_provider_copy_is_not_false_ambiguity(reference, work):
    reference.doi = None
    result = await resolve_reference(
        reference, provider("crossref", [work]), provider("openalex", [work])
    )
    assert result.status == "FOUND" and score(reference, work) == pytest.approx(1)


async def test_two_distinct_identifiers_same_title_are_ambiguous(reference, work):
    reference.doi = None
    other = work.model_copy(update={"doi": "10.1234/other", "id": "other"})
    result = await resolve_reference(
        reference, provider("crossref", [work, other]), provider("openalex", [])
    )
    assert result.status == "AMBIGUOUS"


async def test_not_found_requires_every_provider_and_indexable_title(reference):
    reference.doi = None
    definite = provider("crossref", [])
    assert (
        await resolve_reference(reference, definite, provider("openalex", []))
    ).status == "NOT_FOUND"
    assert (
        await resolve_reference(reference, definite, provider("openalex", [], definitive=False))
    ).status == "CHECK_INCOMPLETE"
    reference.title = "Short title"
    assert (await resolve_reference(reference, definite, definite)).status == "CHECK_INCOMPLETE"
    reference.kind = "book"
    assert (await resolve_reference(reference, definite, definite)).status == "UNCHECKABLE"


async def test_missing_author_does_not_accept_identifier(reference, work):
    reference.authors, reference.title = [], None
    result = await resolve_reference(
        reference, provider("crossref", [work]), provider("openalex", [work])
    )
    assert result.status != "FOUND"


async def test_crossref_mailto_and_cache_ttl():
    payload = {
        "message": {
            "DOI": "10.1234/a",
            "title": ["A real title"],
            "author": [{"family": "Smith"}],
            "published": {"date-parts": [[2024]]},
        }
    }
    with respx.mock(assert_all_called=True) as router:
        route = router.get("https://api.crossref.org/works/10.1234%2Fa").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with Gateway() as gateway:
            result = await Crossref(gateway, "researcher@example.org").lookup("10.1234/a")
            assert result.definitive and result.works[0].year == 2024
            assert route.calls[0].request.url.params["mailto"] == "researcher@example.org"
            expiry, _ = next(iter(gateway.cache.entries.values()))
            assert expiry - gateway.cache.clock() == pytest.approx(30 * DAY, abs=1)


async def test_malformed_provider_data_not_cached():
    async with Gateway(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"message": {"items": [{"bad": "data"}]}})
        )
    ) as gateway:
        result = await Crossref(gateway, "researcher@example.org").search("test")
        assert not result.definitive and not gateway.cache.entries


async def test_openalex_normalization():
    payload = {
        "meta": {"cost_usd": 0},
        "results": [
            {
                "id": "https://openalex.org/W1",
                "title": "A real title",
                "publication_year": 2024,
                "authorships": [{"author": {"display_name": "Jane Smith"}}],
                "doi": "https://doi.org/10.1234/A",
                "is_retracted": False,
                "best_oa_location": {"pdf_url": "https://example.org/a.pdf"},
            }
        ],
    }
    async with Gateway(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    ) as gateway:
        result = await OpenAlex(gateway).search("test")
        assert result.works[0].doi == "10.1234/a"
        assert result.works[0].authors == ["Jane Smith"]
        assert result.works[0].author_names_are_full
        assert result.works[0].is_retracted is False


async def test_arxiv_atom_identifier():
    body = (
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        b"<id>https://arxiv.org/abs/2401.12345</id><title>A test paper</title>"
        b"<published>2024-01-01</published><author><name>Jane Smith</name></author>"
        b"</entry></feed>"
    )
    async with Gateway(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    ) as gateway:
        result = await Arxiv(gateway).lookup("2401.12345")
        assert result.definitive and result.works[0].arxiv == "2401.12345"
        assert not (await Arxiv(gateway).lookup("../../secret")).definitive


def test_retraction_dates_and_missing_sources(work):
    before = RetractionRecord(
        doi=work.doi,
        retracted=date(2023, 1, 1),
        provenance="fixture",
        notice_url="https://doi.org/10.1234/notice",
    )
    after = before.model_copy(update={"retracted": date(2025, 1, 1)})
    assert check_retraction(work, date(2024, 1, 1), [before]).status == "RETRACTED"
    assert check_retraction(work, date(2024, 1, 1), [after]).status == "NOT_RETRACTED"
    assert check_retraction(work, None, [before]).status == "CHECK_INCOMPLETE"
    assert check_retraction(work, date(2024, 1, 1), None).status == "CHECK_INCOMPLETE"
    work.is_retracted = True
    assert check_retraction(work, date(2024, 1, 1), []).status == "CHECK_INCOMPLETE"


def test_watch_csv_uses_original_doi_and_reports_bad_rows():
    rows, rejected = read_watch_csv(
        "OriginalPaperDOI,RetractionDOI,RetractionDate\n10.1234/a,10.1234/notice,01/02/2024\ninvalid,,bad\n10.1234/b,,bad\n"
    )
    assert len(rows) == 2 and rejected == 1
    assert rows[0].doi == "10.1234/a" and rows[0].retracted == date(2024, 1, 2)
    assert rows[1].retracted is None
