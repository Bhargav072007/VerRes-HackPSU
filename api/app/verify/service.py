"""Implement contracts.interfaces.Verify with public, receipt-bearing SupportResult."""

from api.app.ingest.models import ParsedCitation
from api.app.sources.acquire import Source
from api.app.verify.model import Model
from api.app.verify.models import Passage
from api.app.verify.pipeline import verify_citation
from contracts.interfaces import Verify
from contracts.schema import (
    Citation,
    EvidenceLevel,
    MismatchType,
    SourceDocument,
    SupportLabel,
    SupportResult,
)


def needs_review(citation_id: str, reason: str) -> SupportResult:
    return SupportResult(
        citation_id=citation_id,
        label=SupportLabel.NEEDS_REVIEW,
        evidence_strength="INSUFFICIENT",
        reason=reason,
        needs_review_reason=reason,
    )


class VerifyService(Verify):
    def __init__(self, primary: Model | None = None, *, adjudicator: Model | None = None):
        self.primary, self.adjudicator = primary, adjudicator

    async def verify_citation(self, citation: Citation, source: SourceDocument) -> SupportResult:
        if not citation.sentence_ids:
            return needs_review(citation.id, "citation has no source sentence IDs")
        if citation.reference_id != source.reference_id:
            return needs_review(citation.id, "source belongs to a different reference")
        if source.status != "AVAILABLE" or source.evidence_level == EvidenceLevel.METADATA_ONLY:
            return needs_review(citation.id, source.reason)
        if self.primary is None:
            return needs_review(citation.id, "verification model is not configured")
        ids = [p.passage_id for p in source.passages]
        if not ids or len(set(ids)) != len(ids) or any(not p.text.strip() for p in source.passages):
            return needs_review(citation.id, "source passages are missing, empty or duplicated")
        parts = [Passage(id=p.passage_id, text=p.text) for p in source.passages]
        internal = Source(
            work_id=source.reference_id,
            evidence_level="FULL_TEXT"
            if source.evidence_level == EvidenceLevel.FULL_TEXT
            else "ABSTRACT",
            text="\n\n".join(p.text for p in source.passages),
            origin=source.url,
            reason=source.reason,
        )
        parsed = ParsedCitation(
            id=citation.id,
            reference_id=citation.reference_id,
            sentence_id=citation.sentence_ids[0] if citation.sentence_ids else "",
            text=citation.claim_text,
            marker=citation.reference_id,
            section="",
            previous=citation.context or None,
        )
        verification = await verify_citation(
            parsed, internal, self.primary, adjudicator=self.adjudicator, source_passages=parts
        )
        finding = verification.finding
        configured = {
            model.model_id: model for model in (self.adjudicator, self.primary) if model is not None
        }
        models = [configured[mid] for mid in dict.fromkeys(finding.model_ids) if mid in configured]
        reason = finding.reason
        if models:
            reason += (
                " Models: "
                + "; ".join(
                    f"{m.model_id} (vendor={m.vendor or 'unknown'}, family={m.family})"
                    for m in models
                )
                + "."
            )
        if (
            len(models) == 2
            and (models[0].vendor or "").strip().casefold()
            == (models[1].vendor or "").strip().casefold()
        ):
            reason += " second-model check (same vendor)."
        provenance = {
            "model_id": ", ".join(finding.model_ids) or None,
            "prompt_version": finding.prompt_version,
        }
        if finding.status == "NEEDS_REVIEW":
            return needs_review(citation.id, reason).model_copy(update=provenance)
        return SupportResult(
            citation_id=citation.id,
            label=SupportLabel(finding.status),
            mismatch_types=[MismatchType(m) for m in finding.mismatch_types],
            evidence=finding.evidence,
            evidence_strength=finding.evidence_strength,
            reason=reason,
            adjudicated=finding.status in {"NOT_SUPPORTED", "CONTRADICTED"}
            and len(set(finding.model_ids)) == 2,
            **provenance,
        )
