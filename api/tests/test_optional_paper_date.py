from datetime import date

import httpx
import pytest

from api.app.ingest.service import IngestService
from api.app.ingest.tei import parse_tei
from api.app.providers.http import Gateway, Policy


@pytest.mark.parametrize("stamp", [None, "", "2024", "2024-06", "2024-02-30", "invalid"])
async def test_optional_date_does_not_degrade_a_complete_parse(tei, pdf_bytes, stamp):
    original = b'<date when="2025-06-01"/>'
    replacement = f'<date when="{stamp}"/>'.encode() if stamp is not None else b""
    tei = tei.replace(original, replacement)
    async with Gateway(
        {"grobid": Policy("http://grobid:8070", 100, 1, 1)},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=tei)),
        attempts=1,
    ) as gateway:
        paper = await IngestService(gateway).parse_pdf(pdf_bytes())
    assert paper.paper_date is None
    assert paper.status == "PARSED" and paper.needs_review_reason is None
    assert paper.citations and paper.references


def test_valid_publication_date_survives_for_replays(tei):
    parsed = parse_tei(tei)
    assert parsed.paper.published == date(2025, 6, 1) and parsed.status == "FULL"


def test_other_parser_warnings_survive_an_incomplete_date(tei):
    tei = tei.replace(b'when="2025-06-01"', b'when="2025"')
    tei = tei.replace(b'target="#b1"', b'target="#missing"')
    parsed = parse_tei(tei)
    assert parsed.status == "PARTIAL" and parsed.paper.published is None
    assert any("broken" in reason for reason in parsed.reasons)
    assert not any("publication date" in reason for reason in parsed.reasons)
