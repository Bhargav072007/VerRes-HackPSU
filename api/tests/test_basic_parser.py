import io

import pytest
from reportlab.pdfgen.canvas import Canvas

from api.app.ingest.basic import fallback_pdf, marker_numbers, parse_basic_pages
from api.app.ingest.service import IngestService
from api.app.providers.http import Gateway, Policy

TEXT = """Results
Treatment reduced the primary outcome [1,2]. Another finding appears [3].
References
[1] Smith 2024. A controlled study. doi:10.1234/a
[2] Jones 2023. Another study. doi:10.1234/b
[3] Lee 2022. Third study.
"""


def test_basic_parser_keeps_numbered_links_and_excludes_bibliography():
    paper = parse_basic_pages([TEXT])
    assert len(paper.references) == 3 and len(paper.citations) == 3
    assert {c.reference_id for c in paper.citations} == {"b1", "b2", "b3"}
    assert all(s.section == "Results" and "doi:" not in s.text for s in paper.sentences)
    assert paper.references[0].doi == "10.1234/a"
    assert parse_basic_pages([TEXT]) == paper


@pytest.mark.parametrize(
    "marker,expected",
    [
        ("1, 2-4", [1, 2, 3, 4]),
        ("1,1,2", [1, 2]),
        ("4-2", []),
        ("1-9999", []),
        ("not a reference", []),
        ("", []),
    ],
)
def test_numeric_marker_ranges_are_bounded(marker, expected):
    assert marker_numbers(marker) == expected


def test_ambiguous_and_unresolved_references_are_not_invented():
    paper = parse_basic_pages([TEXT + "[1] Conflicting duplicate.\n"])
    assert {r.id for r in paper.references} == {"b2", "b3"}
    assert all(c.reference_id != "b1" for c in paper.citations)
    assert not parse_basic_pages(["A claim [42]."]).citations


async def test_pdfium_fallback_is_explicitly_basic_at_public_boundary():
    import httpx

    output = io.BytesIO()
    canvas = Canvas(output)
    for index, line in enumerate(TEXT.splitlines()):
        canvas.drawString(50, 780 - index * 20, line)
    canvas.save()
    data = output.getvalue()
    parsed = fallback_pdf(data)
    assert parsed.parser == "pypdfium2" and parsed.status == "PARTIAL"
    async with Gateway(
        {"grobid": Policy("http://grobid:8070", 100, 1, 1)},
        attempts=1,
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
    ) as gateway:
        paper = await IngestService(gateway).parse_pdf(data)
    assert paper.status == "NEEDS_REVIEW" and "basic parser" in paper.needs_review_reason
    assert len(paper.references) == 3 and len(paper.citations) == 3


def test_basic_parser_rejects_above_page_limit():
    from pathlib import Path

    path = Path(__file__).parents[2] / "fixtures/pdfs/81_pages.pdf"
    assert fallback_pdf(path.read_bytes()).status == "FAILED"
