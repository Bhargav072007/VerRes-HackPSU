import httpx
import pytest
from app.ingest.pdf import fallback_pdf, ingest_pdf, scan_hidden_text
from app.ingest.tei import identifiers, parse_tei
from app.providers.http import Gateway, Policy


def test_tei_links_context_and_stable_ids(tei):
    parsed = parse_tei(tei)
    assert parsed.status == "FULL"
    assert len(parsed.paper.sentences) == 4
    assert len(parsed.paper.references) == len(parsed.paper.citations) == 1
    reference, citation = parsed.paper.references[0], parsed.paper.citations[0]
    assert (reference.doi, reference.arxiv, reference.pmid) == (
        "10.1234/animal.1",
        "2401.12345",
        "12345678",
    )
    assert citation.reference_id == reference.id
    assert citation.sentence_id == "s00003"
    assert citation.reference_title == reference.title and citation.reference_raw == reference.raw
    assert citation.previous == "We compared treated and control animals."
    assert citation.next == "Further studies are needed."
    assert parse_tei(tei).paper == parsed.paper


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<TEI>",
        b"<TEI/>",
        b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><TEI>&x;</TEI>',
    ],
)
def test_bad_xml_is_structured(data):
    assert parse_tei(data).status == "FAILED"


def test_broken_pointer_and_duplicate_id_partial(tei):
    data = tei.replace(b'target="#b1"', b'target="#missing"')
    result = parse_tei(data)
    assert result.status == "PARTIAL" and not result.paper.citations
    assert any("broken" in r for r in result.reasons)
    duplicate = tei.replace(b"</listBibl>", b'<biblStruct xml:id="b1"/></listBibl>')
    result = parse_tei(duplicate)
    assert result.status == "PARTIAL" and len(result.paper.references) == 1


def test_missing_bibliography(tei):
    data = tei[: tei.index(b"<back>")] + b"</text></TEI>"
    result = parse_tei(data)
    assert result.status == "PARTIAL"
    assert not result.paper.references and not result.paper.citations


def test_fallback_and_hidden_pdf(pdf_bytes):
    benign = pdf_bytes()
    result = fallback_pdf(benign)
    assert result.status == "PARTIAL" and result.paper.sentences
    assert result.paper.references == result.paper.citations == []
    scan = scan_hidden_text(pdf_bytes(hidden=True))
    assert scan.status == "COMPLETE"
    categories = {c for span in scan.spans for c in span.categories}
    assert {
        "WHITE_FILL",
        "TINY_FONT",
        "OFF_PAGE",
        "INVISIBLE_RENDER_MODE",
        "INSTRUCTION_PATTERN",
    } <= categories
    assert not scan_hidden_text(benign).spans


@pytest.mark.parametrize("data", [b"not a pdf", b"%PDF-broken"])
def test_bad_pdf_does_not_raise(data):
    assert fallback_pdf(data).status == "FAILED"
    assert scan_hidden_text(data).status == "CHECK_INCOMPLETE"


async def test_grobid_timeout_falls_back(pdf_bytes):
    def handler(request):
        assert b"consolidateCitations" in request.content
        assert request.extensions["timeout"]["read"] == 60
        raise httpx.ReadTimeout("fixture timeout")

    async with Gateway(
        {"grobid": Policy("http://grobid:8070", 100, 1, 1)},
        transport=httpx.MockTransport(handler),
        attempts=1,
    ) as gateway:
        parsed = await ingest_pdf(pdf_bytes(), gateway)
    assert parsed.status == "PARTIAL" and parsed.parser == "pdfplumber"


def test_identifier_regex():
    assert identifiers("https://doi.org/10.1000/test.")["doi"] == "10.1000/test"


def test_shared_marker_keeps_selected_reference_metadata(tei):
    data = tei.replace(b'target="#b1"', b'target="#b1 #b2"')
    data = data.replace(
        b"</listBibl>",
        b'<biblStruct xml:id="b2"><analytic>'
        b"<title>Another work</title></analytic></biblStruct></listBibl>",
    )
    citations = parse_tei(data).paper.citations
    assert len(citations) == 2
    assert {c.reference_title for c in citations} == {
        "Controlled animal intervention study",
        "Another work",
    }
    assert citations[0].marker == citations[1].marker
