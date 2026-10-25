import html
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from reportlab.pdfgen.canvas import Canvas

from api.app.orchestrator import build_services
from api.app.providers.models import HTTPResult, Work
from api.app.review.panel import ReviewPanel
from api.app.settings import Settings
from api.app.sources.acquire import PARTIAL_PDF_PREFIX, extract_full_pdf, extract_pdf_text
from api.app.sources.service import SourceService
from api.app.verify.outcomes import BACKGROUND_REASON, METHOD_REASON, informational_citation
from api.app.verify.service import VerifyService
from api.tests.helpers import FixtureModel, judgment
from contracts.schema import (
    Citation,
    ExistenceResult,
    Paper,
    Reference,
    SourceDocument,
    SourcePassage,
)


@pytest.fixture
def graphic_source():
    output = io.BytesIO()
    canvas = Canvas(output)
    canvas.drawString(50, 780, "Controlled animal intervention study")
    canvas.drawString(50, 760, "Smith")
    canvas.drawString(50, 720, "The treatment reduced inflammation in mice by 20 percent.")
    canvas.rect(50, 100, 200, 100)
    canvas.save()
    return output.getvalue()


@pytest.mark.parametrize(
    "label,expected", [("SUPPORTED", "SUPPORTED"), ("NOT_SUPPORTED", "NEEDS_REVIEW")]
)
async def test_graphical_pdf_preserves_usable_prose_but_not_absence_verdicts(
    graphic_source, claim, label, expected
):
    reference = Reference(
        id="r1",
        raw_text="Controlled study",
        title="Controlled animal intervention study",
        authors=["Smith"],
        url="https://example.org/paper.pdf",
    )
    gateway = SimpleNamespace(
        safe_fetch=AsyncMock(return_value=HTTPResult(status=200, content=graphic_source))
    )
    document = await SourceService(gateway).fetch_source(
        ExistenceResult(
            reference_id="r1", status="VERIFIED", matched_reference=reference, reason="matched"
        )
    )
    assert document.status == "AVAILABLE" and document.passages
    assert document.reason.startswith(PARTIAL_PDF_PREFIX)
    assert document.passages[0].section == "Extracted text (partial coverage)"
    if label == "NOT_SUPPORTED":
        document.reason = "Readable prose; reason changed by a caller"
        # Passage metadata still prevents a caller from silently upgrading coverage.
    assert (
        extract_full_pdf(
            graphic_source,
            Work(provider="fixture", id="r1", title=reference.title, authors=reference.authors),
        )
        is None
    )
    model = FixtureModel(
        {
            "classify": {"items": [{"citation_id": "c1", "function": "SPECIFIC_CLAIM"}]},
            "split": {"ambiguous": False, "claims": [claim.model_dump()]},
            "judge": judgment(label).model_dump(),
        }
    )
    result = await VerifyService(model).verify_citation(
        Citation(id="c1", reference_id="r1", sentence_ids=["s1"], claim_text=claim.text), document
    )
    assert result.label == expected
    if label == "SUPPORTED":
        assert result.evidence[0].quote in document.passages[0].text
    else:
        assert "complete source coverage" in result.reason and not result.evidence
    judge_call = next(c for c in model.calls if c["task"] == "judge")
    assert '"whole_source_coverage": false' in html.unescape(judge_call["data"])


def test_scanned_headers_still_do_not_qualify_for_text_coverage():
    from api.tests.test_correctness_fixes import raster_body_pdf

    work = Work(
        provider="fixture", id="r1", title="Controlled animal intervention study", authors=["Smith"]
    )
    assert extract_pdf_text(raster_body_pdf(), work) is None


@pytest.mark.parametrize(
    "function,reason", [("BACKGROUND", BACKGROUND_REASON), ("METHOD_OR_TOOL", METHOD_REASON)]
)
async def test_informational_citation_is_identified_even_without_source_text(function, reason):
    model = FixtureModel({"classify": {"items": [{"citation_id": "c1", "function": function}]}})
    citation = Citation(
        id="c1",
        reference_id="r1",
        sentence_ids=["s1"],
        claim_text="We use the published method [1].",
    )
    result = await VerifyService(model).verify_citation(
        citation,
        SourceDocument(
            reference_id="r1",
            evidence_level="METADATA_ONLY",
            status="CHECK_INCOMPLETE",
            reason="No accessible text",
        ),
    )
    assert informational_citation(result) and result.needs_review_reason == reason
    assert [c["task"] for c in model.calls] == ["classify"]
    paper = Paper(id="p", citations=[citation])
    panel = ReviewPanel(model)
    assert panel.citation_table(paper, [result])[0]["support_label"] == "NOT_APPLICABLE"
    assert not informational_citation(
        result.model_copy(update={"needs_review_reason": "model failed"})
    )


async def test_specific_claim_without_source_is_not_treated_as_informational():
    model = FixtureModel(
        {"classify": {"items": [{"citation_id": "c1", "function": "SPECIFIC_CLAIM"}]}}
    )
    result = await VerifyService(model).verify_citation(
        Citation(
            id="c1",
            reference_id="r1",
            sentence_ids=["s1"],
            claim_text="Treatment improves outcomes.",
        ),
        SourceDocument(
            reference_id="r1",
            evidence_level="METADATA_ONLY",
            status="CHECK_INCOMPLETE",
            reason="Publisher unavailable",
        ),
    )
    assert not informational_citation(result)
    assert result.label == "NEEDS_REVIEW" and "Publisher unavailable" in result.reason


async def test_classifier_can_recover_from_wrong_ids(citation):
    from api.app.verify.pipeline import classify_citations

    answers = iter(
        [
            {"items": [{"citation_id": "wrong", "function": "BACKGROUND"}]},
            {"items": [{"citation_id": citation.id, "function": "BACKGROUND"}]},
        ]
    )
    model = FixtureModel({"classify": lambda _: json.dumps(next(answers))})
    assert await classify_citations([citation], model) == {citation.id: "BACKGROUND"}
    assert len(model.calls) == 2


async def test_available_abstract_is_always_included_with_retrieved_body_passages(claim):
    model = FixtureModel(
        {
            "classify": {"items": [{"citation_id": "c1", "function": "SPECIFIC_CLAIM"}]},
            "split": {"ambiguous": False, "claims": [claim.model_dump()]},
            "judge": judgment().model_dump(),
        }
    )
    document = SourceDocument(
        reference_id="r1",
        evidence_level="FULL_TEXT",
        reason="identity matched",
        passages=[
            SourcePassage(passage_id=f"p{i:05d}", text="treatment inflammation mice " * 100)
            for i in range(1, 10)
        ]
        + [
            SourcePassage(
                passage_id="abstract", text="A separate abstract that must remain available."
            )
        ],
    )
    await VerifyService(model).verify_citation(
        Citation(id="c1", reference_id="r1", sentence_ids=["s1"], claim_text=claim.text), document
    )
    data = html.unescape(next(c for c in model.calls if c["task"] == "judge")["data"])
    assert '"id": "abstract"' in data


async def test_model_names_load_from_dotenv(monkeypatch, tmp_path):
    for name in ("STUBS", "MODEL_PRIMARY", "MODEL_ADJUDICATOR", "REVIEW_MODEL"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "models.env"
    env.write_text("MODEL_PRIMARY=fixture-primary\nMODEL_ADJUDICATOR=fixture-second\n")
    settings = Settings(_env_file=env, openai_api_key="fixture-key", crossref_mailto=None)
    services = build_services(settings)
    try:
        assert services.primary_model.model_id == "fixture-primary"
        assert services.adjudicator_model.model_id == "fixture-second"
    finally:
        await services.aclose()
