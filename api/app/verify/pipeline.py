import asyncio

from pydantic import ValidationError

from api.app.ingest.models import ParsedCitation
from api.app.sources.acquire import Source
from api.app.verify.gates import SEVERE, aggregate, gate, normalize_quote, uncertain
from api.app.verify.model import Model, ModelFailure, call_model
from api.app.verify.models import (
    CitationVerification,
    ClaimSplit,
    Classification,
    Judgment,
    Passage,
)
from api.app.verify.retrieval import passages, retrieve, retrieve_passages


async def classify_citations(citations: list[ParsedCitation], model: Model) -> dict[str, str]:
    classifications = {}
    for start in range(0, len(citations), 10):
        batch = citations[start : start + 10]
        try:
            result = await call_model(
                model, "classify", [c.model_dump() for c in batch], Classification
            )
            ids = [item.citation_id for item in result.items]
            expected = {c.id for c in batch}
            if len(ids) != len(expected) or set(ids) != expected:
                continue
            classifications.update({i.citation_id: i.function for i in result.items})
        except (ModelFailure, ValidationError):
            continue
    return classifications


async def verify_citation(
    citation: ParsedCitation,
    source: Source,
    primary: Model,
    *,
    adjudicator: Model | None = None,
    citation_function=None,
    source_passages: list[Passage] | None = None,
):
    result = CitationVerification(
        citation_id=citation.id,
        finding=uncertain(source, "verification has not completed"),
        citation_function=citation_function,
    )
    if citation_function is None:
        functions = await classify_citations([citation], primary)
        result.citation_function = functions.get(citation.id)
    if not result.citation_function:
        result.finding = uncertain(source, "citation function classification failed")
        return result
    if result.citation_function in {"BACKGROUND", "METHOD_OR_TOOL"}:
        result.finding = uncertain(source, "citation does not attribute a specific finding")
        return result
    if source.evidence_level == "NONE":
        result.finding = uncertain(source, "source evidence is unavailable")
        return result
    try:
        split = await call_model(primary, "split", citation.model_dump(), ClaimSplit)
    except (ModelFailure, ValidationError):
        result.finding = uncertain(
            source, "atomic claim output failed schema validation", [primary.model_id]
        )
        return result
    if split.ambiguous:
        result.finding = uncertain(
            source, "attribution to the marked source is ambiguous", [primary.model_id]
        )
        return result
    result.claims = split.claims
    for claim in split.claims:
        if claim.magnitude and normalize_quote(claim.magnitude) not in normalize_quote(
            citation.text
        ):
            result.claim_findings.append(
                uncertain(source, "splitter introduced a magnitude absent from the citing sentence")
            )
            continue
        if source_passages is None:
            selected = await asyncio.to_thread(retrieve, claim.text, source.text, source.abstract)
        else:
            selected = await asyncio.to_thread(retrieve_passages, claim.text, source_passages)
        try:
            judgment = await call_model(
                primary,
                "judge",
                {
                    "claim": claim.model_dump(),
                    "evidence_level": source.evidence_level,
                    "passages": [p.model_dump() for p in selected],
                },
                Judgment,
            )
        except (ModelFailure, ValidationError):
            result.claim_findings.append(
                uncertain(source, "judge output failed schema validation", [primary.model_id])
            )
            continue
        finding = gate(judgment, selected, source, primary.model_id)
        if judgment.label in SEVERE and source.evidence_level == "FULL_TEXT":
            # Confirm primary evidence BEFORE spending an independent full-source call.
            proposed = gate(judgment, selected, source, primary.model_id, adjudicated=True)
            if proposed.status in SEVERE:
                if (
                    not adjudicator
                    or not primary.family.strip()
                    or not adjudicator.family.strip()
                    or adjudicator.family.strip().casefold() == primary.family.strip().casefold()
                    or adjudicator.model_id == primary.model_id
                ):
                    finding = uncertain(
                        source,
                        "a different-family adjudicator is not configured",
                        [primary.model_id],
                    )
                else:
                    whole_source = (
                        source_passages if source_passages is not None else passages(source.text)
                    )
                    try:
                        second = await call_model(
                            adjudicator,
                            "adjudicate",
                            {
                                "claim": claim.model_dump(),
                                "evidence_level": "FULL_TEXT",
                                "passages": [p.model_dump() for p in whole_source],
                            },
                            Judgment,
                        )
                        checked = gate(
                            second, whole_source, source, adjudicator.model_id, adjudicated=True
                        )
                        if checked.status == proposed.status:
                            finding = proposed.model_copy(
                                update={
                                    "model_ids": [primary.model_id, adjudicator.model_id],
                                    "evidence": proposed.evidence + checked.evidence,
                                    "passages": list(
                                        {
                                            p.id: p for p in proposed.passages + checked.passages
                                        }.values()
                                    ),
                                }
                            )
                        else:
                            finding = uncertain(
                                source,
                                "models disagree or adjudicator evidence failed",
                                [primary.model_id, adjudicator.model_id],
                            )
                    except (ModelFailure, ValidationError):
                        finding = uncertain(
                            source,
                            "adjudicator output failed schema validation",
                            [primary.model_id, adjudicator.model_id],
                        )
        result.claim_findings.append(finding)
    result.finding = aggregate(result.claim_findings, source)
    return result
