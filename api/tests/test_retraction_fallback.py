import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from api.app.providers.http import Gateway
from api.app.providers.metadata import Crossref, crossref_work
from api.app.providers.models import Work
from api.app.resolve.retraction import crossref_notices
from api.app.resolve.service import ResolveService
from api.tests.test_shared_interfaces import provider
from contracts.schema import ExistenceResult, Reference

DOI = "10.1016/s0140-6736(97)11096-0"
NOTICE = "https://doi.org/10.1016/s0140-6736%2810%2960175-4"
FIXTURE = Path(__file__).parent / "fixtures" / "wakefield-crossref.json"


async def run_check(payload, *, citing=date(2026, 10, 25), retracted=True, watch=None):
    original = crossref_work(json.loads(FIXTURE.read_text())["message"])
    reference = Reference(
        id="b0",
        raw_text=original.title,
        title=original.title,
        doi=DOI,
        authors=original.authors,
        year=original.year,
    )
    existence = ExistenceResult(
        reference_id="b0", status="VERIFIED", matched_reference=reference, reason="offline fixture"
    )
    alex = original.model_copy(
        update={"provider": "openalex", "id": "W1", "is_retracted": retracted}
    )
    async with Gateway(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(503)
            if payload is None
            else httpx.Response(200, json=payload)
        ),
        attempts=1,
    ) as gateway:
        service = ResolveService(
            Crossref(gateway, "tests@example.org"), provider("openalex", [alex]), retractions=watch
        )
        return await service.check_retraction(existence, citing)


@pytest.mark.parametrize("retracted", [True, False, None])
async def test_live_crossref_receipt_without_loaded_csv(retracted):
    result = await run_check(json.loads(FIXTURE.read_text()), retracted=retracted)
    assert result.status == "RETRACTED"
    assert NOTICE in result.notice_urls
    assert result.reason == "cited work was retracted (2010); retraction date: 2010-02-06"
    assert result.source_type == "crossref" and result.source_url == NOTICE


@pytest.mark.parametrize(
    "citing,status",
    [(date(2003, 1, 1), "NONE"), (date(2005, 1, 1), "CORRECTED"), (None, "UNKNOWN")],
)
async def test_notice_chronology_is_preserved(citing, status):
    assert (await run_check(json.loads(FIXTURE.read_text()), citing=citing)).status == status


@pytest.mark.parametrize(
    "updates",
    [[], [{"type": "retraction", "DOI": "10.1234/notice", "updated": {"date-parts": [[2010]]}}]],
)
async def test_positive_openalex_flag_has_an_explicit_undated_receipt(updates):
    payload = json.loads(FIXTURE.read_text())
    payload["message"]["updated-by"] = updates
    result = await run_check(payload)
    assert result.status == "RETRACTED"
    assert result.reason == "Marked retracted by OpenAlex; notice date unavailable"
    assert result.source_url == "https://openalex.org/W1"
    assert result.source_type == "openalex"


async def test_csv_is_last_fallback_when_crossref_unavailable():
    original = crossref_work(json.loads(FIXTURE.read_text())["message"])
    watch = type("Store", (), {"lookup": AsyncMock(return_value=crossref_notices(original, DOI))})()
    assert (await run_check(None, watch=watch)).status == "RETRACTED"
    watch.lookup.assert_awaited_once_with(DOI)
    assert (await run_check(None)).status == "RETRACTED"


async def test_openalex_false_and_crossref_no_updates():
    payload = json.loads(FIXTURE.read_text())
    payload["message"].pop("updated-by")
    assert (await run_check(payload, retracted=False)).status == "NONE"


@pytest.mark.parametrize(
    "stamp",
    [
        None,
        [],
        {"date-parts": None},
        {"date-parts": [None]},
        {"date-parts": [[2010, 99, 6]]},
        {"date-parts": [[True, 2, 6]]},
    ],
)
def test_malformed_dates_stay_unknown(stamp):
    work = Work(
        provider="crossref",
        id=DOI,
        doi=DOI,
        updated_by=[{"type": "retraction", "DOI": "10.1234/notice", "updated": stamp}],
    )
    assert crossref_notices(work, DOI)[0].retracted is None


def test_notice_relationship_direction_and_type():
    update = {"DOI": DOI, "type": "retraction", "updated": {"date-parts": [[2010, 2, 6]]}}
    notice = Work(
        provider="crossref", id="10.1234/notice", doi="10.1234/notice", update_to=[update]
    )
    assert crossref_notices(notice, DOI)[0].retracted == date(2010, 2, 6)
    assert crossref_notices(notice, "10.1234/other") == []
    notice.doi = DOI
    assert crossref_notices(notice, DOI) is None
    notice.updated_by = [{**update, "DOI": "10.1234/notice", "type": "new-version"}]
    assert crossref_notices(notice, DOI) == []


async def test_notice_lookup_fills_undated_stub():
    original = crossref_work(json.loads(FIXTURE.read_text())["message"])
    original.updated_by = [{"DOI": "10.1234/notice", "type": "retraction"}]
    notice = Work(
        provider="crossref",
        id="10.1234/notice",
        doi="10.1234/notice",
        update_to=[{"DOI": DOI, "type": "retraction", "updated": {"date-parts": [[2010, 2, 6]]}}],
    )
    crossref = provider("crossref", [original])
    crossref.lookup.side_effect = [
        await provider("crossref", [original]).lookup(DOI),
        await provider("crossref", [notice]).lookup(notice.doi),
    ]
    reference = Reference(
        id="b0",
        raw_text=original.title,
        title=original.title,
        doi=DOI,
        authors=original.authors,
        year=original.year,
    )
    existence = ExistenceResult(
        reference_id="b0", status="VERIFIED", matched_reference=reference, reason="offline fixture"
    )
    service = ResolveService(
        crossref, provider("openalex", [original.model_copy(update={"is_retracted": True})])
    )
    result = await service.check_retraction(existence, date(2026, 10, 25))
    assert result.status == "RETRACTED"
    assert result.notice_urls == ["https://doi.org/10.1234/notice"]
