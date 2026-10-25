import html
import json

import pytest

from api.app.sources.acquire import Source
from api.app.verify.gates import gate
from api.app.verify.models import AtomicClaim, Passage
from api.app.verify.service import VerifyService
from api.tests.helpers import FixtureModel, judgment
from contracts.schema import Citation, MismatchType, SourceDocument, SourcePassage

QUOTE = "vaccinations are not associated with the development of autism or autism spectrum disorder"


async def check(
    *,
    first="CONTRADICTED",
    second="CONTRADICTED",
    mismatches=None,
    bad_quote=False,
    strength="DIRECT",
):
    citation = Citation(
        id="taylor-citation",
        reference_id="taylor-2014",
        sentence_ids=["s1"],
        claim_text=(
            "The meta-analysis is cited as showing a weak positive association "
            "between vaccination and autism [2]."
        ),
    )
    source = SourceDocument(
        reference_id="taylor-2014",
        evidence_level="ABSTRACT_ONLY",
        passages=[SourcePassage(passage_id="abstract", text=QUOTE)],
        url="https://doi.org/10.1016/j.vaccine.2014.04.085",
        reason="authentic abstract excerpt",
    )
    claim = AtomicClaim(
        text="Vaccination has a positive association with autism.",
        subject_or_population="children",
        exposure_or_intervention="vaccination",
        outcome="autism",
        direction="increase",
        magnitude=None,
        relation="associative",
        hedge="definite",
        scope_or_time=None,
    )
    primary_judgment = judgment(
        first, passage_id="abstract", quote="this quote does not exist" if bad_quote else QUOTE
    )
    primary_judgment.mismatch_types = [
        MismatchType(m) for m in (["DIRECTION"] if mismatches is None else mismatches)
    ]
    primary_judgment.evidence_strength = strength
    second_judgment = judgment(second, passage_id="abstract", quote=QUOTE)
    second_judgment.mismatch_types = [MismatchType.DIRECTION]
    primary = FixtureModel(
        {
            "classify": {"items": [{"citation_id": citation.id, "function": "SPECIFIC_CLAIM"}]},
            "split": {"ambiguous": False, "claims": [claim.model_dump()]},
            "judge": primary_judgment.model_dump(),
        },
        model_id="first",
        family="fixture-a",
        vendor="fixture-a",
    )
    adjudicator = FixtureModel(
        {"adjudicate": second_judgment.model_dump()},
        model_id="second",
        family="fixture-b",
        vendor="fixture-b",
    )
    result = await VerifyService(primary, adjudicator=adjudicator).verify_citation(citation, source)
    return result, adjudicator


async def test_taylor_explicit_opposite_finding_requires_verified_quotes_and_second_model():
    result, model = await check()
    assert result.label == "CONTRADICTED" and result.adjudicated
    assert result.evidence_level == "ABSTRACT_ONLY"
    assert result.reason.startswith("Contradicted by the abstract.")
    assert all(q.quote == QUOTE and q.evidence_level == "ABSTRACT_ONLY" for q in result.evidence)
    assert result.prompt_version == "v3"
    call = model.calls[0]
    data = json.loads(html.unescape(call["data"].split(">", 1)[1].rsplit("</untrusted>", 1)[0]))
    assert data["evidence_level"] == "ABSTRACT"
    assert data["passages"][0]["text"] == QUOTE


@pytest.mark.parametrize("mismatches", [["SCOPE"], ["MAGNITUDE"], ["DIRECTION", "SCOPE"], []])
async def test_scope_or_magnitude_only_abstract_mismatch_is_needs_review(mismatches):
    result, model = await check(mismatches=mismatches)
    assert result.label == "NEEDS_REVIEW" and not model.calls


async def test_abstract_not_supported_keeps_precise_abstention_reason():
    result, model = await check(first="NOT_SUPPORTED")
    assert result.label == "NEEDS_REVIEW" and not model.calls
    assert result.reason.startswith("abstract does not address this claim; full text unavailable")


async def test_adjudicator_disagreement_abstains():
    result, model = await check(second="SUPPORTED")
    assert result.label == "NEEDS_REVIEW" and len(model.calls) == 1


@pytest.mark.parametrize("changes", [{"bad_quote": True}, {"strength": "INDIRECT"}])
async def test_unverified_or_indirect_abstract_evidence_never_reaches_adjudicator(changes):
    result, model = await check(**changes)
    assert result.label == "NEEDS_REVIEW" and not model.calls


def test_primary_direction_label_cannot_skip_second_model():
    source = Source(work_id="taylor", evidence_level="ABSTRACT", text=QUOTE, reason="abstract")
    proposed = judgment("CONTRADICTED", quote=QUOTE, passage_id="abstract")
    proposed.mismatch_types = [MismatchType.DIRECTION]
    assert (
        gate(proposed, [Passage(id="abstract", text=QUOTE)], source, "primary").status
        == "NEEDS_REVIEW"
    )
