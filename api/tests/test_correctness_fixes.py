"""Regression cases from the architecture review; all documents/models are synthetic."""

import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from api.app.graph.service import validate_claim_map
from api.app.ingest.pdf import fallback_pdf, valid_pdf
from api.app.providers.metadata import openalex_work
from api.app.providers.models import Work
from api.app.resolve.existence import agrees, metadata_mismatch, resolve_reference
from api.app.sources.acquire import acquire_source, extract_full_pdf
from api.app.verify.gates import gate, quote_matches
from api.app.verify.model import ModelFailure, call_model
from api.app.verify.models import Judgment
from api.app.verify.pipeline import independent_models, verify_citation
from api.app.verify.retrieval import passages
from api.tests.helpers import FixtureModel, judgment
from api.tests.test_resolution import provider
from api.tests.test_resolution import reference as reference_fixture
from api.tests.test_verify import responses
from contracts.schema import Citation, ClaimMap, ClaimNode, Paper, Sentence

reference = reference_fixture


@pytest.mark.parametrize(
    "actual,proposed",
    [
        ("wasn't effective", "was effective"),
        ("isn't effective", "is effective"),
        ("statistically insignificant", "statistically significant"),
        ("-5 points", "+5 points"),
        ("5.0 percent", "5.1 percent"),
        ("10 mM", "10 mm"),
        ("10⁵ points", "105 points"),
    ],
)
def test_meaning_changing_quotes_never_establish_support(source, actual, proposed):
    template = "The primary result was {} among all participants in the randomized study."
    source.text = template.format(actual)
    quote = template.format(proposed)
    assert not quote_matches(quote, source.text)
    assert gate(judgment(quote=quote), passages(source.text), source, "m").status == "NEEDS_REVIEW"


@pytest.mark.parametrize(
    "quote,source",
    [
        ("effective in all enrolled patients", "ineffective in all enrolled patients"),
        ("5 points among all patients", "-5 points among all patients"),
        ("The change was 5", "The change was 5.5 percent"),
        ("The change was 10", "The change was 10^5 percent"),
    ],
)
def test_quote_boundaries_cannot_crop_words_or_numbers(quote, source):
    assert not quote_matches(quote, source)


def test_quotes_allow_typography_and_whitespace_only():
    assert quote_matches("The study’s finding was clear.", "The study's\nfinding  was clear.")


def raster_body_pdf():
    output = io.BytesIO()
    canvas = Canvas(output)
    image = ImageReader(Image.new("RGB", (300, 300), "white"))
    canvas.drawString(50, 780, "Controlled animal intervention study")
    canvas.drawString(50, 760, "Smith")
    canvas.drawImage(image, 50, 100, width=450, height=600)
    canvas.showPage()
    canvas.drawString(50, 780, "Journal of Medicine - 2")
    canvas.drawImage(image, 50, 100, width=450, height=600)
    canvas.save()
    return output.getvalue()


async def test_raster_body_cannot_qualify_as_full_text():
    work = Work(
        provider="openalex",
        id="W1",
        title="Controlled animal intervention study",
        authors=["Smith"],
        oa_url="https://example.org/paper.pdf",
        abstract="An actual abstract.",
    )
    data = raster_body_pdf()
    assert extract_full_pdf(data, work) is None
    from api.app.providers.models import HTTPResult

    gateway = type(
        "Gateway", (), {"safe_fetch": AsyncMock(return_value=HTTPResult(status=200, content=data))}
    )()
    result = await acquire_source(work, gateway)
    assert result.evidence_level == "ABSTRACT" and result.text == work.abstract


def test_intake_size_is_supported_by_ingest(pdf_bytes):
    data = pdf_bytes()
    padded = data.replace(b"%%EOF", b"%" + b" " * (21 * 1024 * 1024) + b"\n%%EOF")
    assert valid_pdf(padded)
    assert fallback_pdf(padded).status == "PARTIAL"
    assert not valid_pdf(data + b" " * (25 * 1024 * 1024 + 1 - len(data)))


def test_vector_only_body_is_not_whole_source_evidence():
    output = io.BytesIO()
    canvas = Canvas(output)
    canvas.drawString(50, 780, "Controlled animal intervention study")
    canvas.drawString(50, 760, "Smith")
    canvas.rect(50, 100, 450, 600, fill=1)
    canvas.save()
    work = Work(
        provider="openalex",
        id="W1",
        title="Controlled animal intervention study",
        authors=["Smith"],
    )
    assert extract_full_pdf(output.getvalue(), work) is None


@pytest.mark.parametrize(
    "surname,display",
    [
        ("de Vries", "Johannes de Vries"),
        ("van der Waals", "Johannes van der Waals"),
        ("García Márquez", "Gabriel García Márquez"),
    ],
)
def test_display_name_does_not_invent_a_doi_mismatch(reference, surname, display):
    reference.authors = [surname]
    work = openalex_work(
        {
            "id": "W1",
            "doi": reference.doi,
            "title": reference.title,
            "publication_year": reference.year,
            "authorships": [{"author": {"display_name": display}}],
        }
    )
    assert agrees(reference, work)
    assert not metadata_mismatch(reference, work)


def test_uncertain_display_name_is_not_an_author_discrepancy(reference):
    work = openalex_work(
        {
            "id": "W1",
            "doi": reference.doi,
            "title": reference.title,
            "publication_year": reference.year,
            "authorships": [{"author": {"display_name": "Unparsed Organization"}}],
        }
    )
    assert not agrees(reference, work)
    assert not metadata_mismatch(reference, work)


async def test_full_display_name_and_structured_family_corroborate_one_doi(reference):
    reference.authors = ["de Vries"]
    crossref = Work(
        provider="crossref",
        id=reference.doi,
        doi=reference.doi,
        title=reference.title,
        authors=reference.authors,
        year=reference.year,
    )
    openalex = openalex_work(
        {
            "id": "W1",
            "doi": reference.doi,
            "title": reference.title,
            "publication_year": reference.year,
            "authorships": [{"author": {"display_name": "Johannes de Vries"}}],
            "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"},
        }
    )
    result = await resolve_reference(
        reference, provider("crossref", [crossref]), provider("openalex", [openalex])
    )
    assert result.status == "FOUND" and result.work.authors == ["de Vries"]
    assert result.work.oa_url == openalex.oa_url


def test_graph_cannot_attach_a_citation_from_an_unrelated_sentence():
    paper = Paper(
        id="p",
        sentences=[Sentence(id="s1", text="One"), Sentence(id="s2", text="Two")],
        citations=[Citation(id="c1", reference_id="b1", sentence_ids=["s2"], claim_text="Two")],
    )
    proposal = ClaimMap(
        paper_id="p",
        nodes=[ClaimNode(id="n1", text="One", sentence_ids=["s1"], citation_ids=["c1"])],
    )
    checked = validate_claim_map(proposal, paper)
    assert checked.status == "NEEDS_REVIEW" and not checked.nodes


async def test_judge_cannot_return_more_than_three_quotes(source):
    answer = judgment().model_dump()
    answer["evidence"] *= 4
    model = FixtureModel({"judge": answer})
    with pytest.raises(ModelFailure, match="three"):
        await call_model(model, "judge", {}, Judgment)
    assert model.calls[0]["schema"]["properties"]["evidence"]["maxItems"] == 3
    finding = gate(Judgment.model_validate(answer), passages(source.text), source, "m")
    assert finding.status == "NEEDS_REVIEW"


@pytest.mark.parametrize("first,second", [("OpenAI", " openai "), ("OpenAI", ""), ("", "Other")])
async def test_severe_findings_require_known_distinct_vendors(
    citation, source, claim, first, second
):
    primary = FixtureModel(responses(claim, "CONTRADICTED"), vendor=first)
    other = FixtureModel({}, model_id="other", family="other-family", vendor=second)
    result = await verify_citation(citation, source, primary, adjudicator=other)
    assert result.finding.status == "NEEDS_REVIEW" and not other.calls
    assert "vendor" in result.finding.reason


def test_independence_checks_each_configured_identity():
    primary = FixtureModel({}, model_id="m1", family="f1", vendor="v1")
    other = FixtureModel({}, model_id="m2", family="f2", vendor="v2")
    assert independent_models(primary, other)
    for name in ("model_id", "family", "vendor"):
        previous = getattr(other, name)
        setattr(other, name, getattr(primary, name))
        assert not independent_models(primary, other)
        setattr(other, name, previous)
