"""Shared API and LLM schemas. Frozen after A1; changes require a proposal."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExistenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    VERIFIED_WITH_DISCREPANCIES = "VERIFIED_WITH_DISCREPANCIES"
    DOI_MISMATCH = "DOI_MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNCHECKABLE = "UNCHECKABLE"
    CHECK_INCOMPLETE = "CHECK_INCOMPLETE"


class RetractionStatus(StrEnum):
    RETRACTED = "RETRACTED"
    EXPRESSION_OF_CONCERN = "EXPRESSION_OF_CONCERN"
    CORRECTED = "CORRECTED"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class EvidenceLevel(StrEnum):
    FULL_TEXT = "FULL_TEXT"
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    METADATA_ONLY = "METADATA_ONLY"


class Provenance(Contract):
    source_url: str | None = None
    source_type: (
        Literal["crossref", "openalex", "arxiv", "retraction_watch", "publisher"] | None
    ) = None
    retrieved_at: datetime | None = None
    evidence_level: EvidenceLevel | None = None
    quote_offsets: list[tuple[int, int]] | None = Field(
        default=None, description="Producer-supplied half-open character ranges in the source."
    )
    model_id: str | None = None
    prompt_version: str | None = None


class SupportLabel(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class MismatchType(StrEnum):
    SCOPE = "SCOPE"
    POPULATION = "POPULATION"
    MAGNITUDE = "MAGNITUDE"
    CAUSAL_OVERREACH = "CAUSAL_OVERREACH"
    HEDGE_DROPPED = "HEDGE_DROPPED"
    DIRECTION = "DIRECTION"
    TEMPORAL = "TEMPORAL"
    METHOD = "METHOD"
    SOURCE_LIMITATION = "SOURCE_LIMITATION"
    NOT_IN_SOURCE = "NOT_IN_SOURCE"


class Reference(Contract):
    id: str
    raw_text: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None


class Sentence(Contract):
    id: str
    text: str
    section: str | None = None
    page: int | None = Field(default=None, ge=1)


class Citation(Contract):
    id: str
    reference_id: str
    sentence_ids: list[str]
    claim_text: str
    context: str = ""


class Paper(Contract):
    id: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    paper_date: date | None = None
    sentences: list[Sentence] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    status: Literal["PARSED", "NEEDS_REVIEW"] = "PARSED"
    needs_review_reason: str | None = None


class ExistenceResult(Provenance):
    reference_id: str
    status: ExistenceStatus
    matched_reference: Reference | None = None
    candidates: list[Reference] = Field(default_factory=list)
    provider_ids: dict[str, str] = Field(default_factory=dict)
    receipt_urls: list[str] = Field(default_factory=list)
    discrepancies: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class RetractionResult(Provenance):
    reference_id: str
    status: RetractionStatus
    notice_urls: list[str] = Field(default_factory=list)
    checked_as_of: date | None = None
    reason: str = Field(min_length=1)


class SourcePassage(Contract):
    passage_id: str
    text: str
    section: str | None = None
    page: int | None = Field(default=None, ge=1)


class SourceDocument(Provenance):
    reference_id: str
    evidence_level: EvidenceLevel
    passages: list[SourcePassage] = Field(default_factory=list)
    url: str | None = None
    content_sha256: str | None = None
    status: Literal["AVAILABLE", "CHECK_INCOMPLETE"] = "AVAILABLE"
    reason: str = Field(min_length=1)


class EvidenceSpan(Provenance):
    passage_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class Judgment(Provenance):
    label: SupportLabel
    mismatch_types: list[MismatchType] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    evidence_strength: Literal["DIRECT", "INDIRECT", "INSUFFICIENT"]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_receipts(self) -> Self:
        if self.label != SupportLabel.NEEDS_REVIEW and (
            not self.evidence or self.evidence_strength == "INSUFFICIENT"
        ):
            raise ValueError("A verdict requires evidence of support strength; use NEEDS_REVIEW")
        return self


class SupportResult(Judgment):
    citation_id: str
    needs_review_reason: str | None = None
    adjudicated: bool = False

    @model_validator(mode="after")
    def require_review_reason(self) -> Self:
        if self.label == SupportLabel.NEEDS_REVIEW and not self.needs_review_reason:
            raise ValueError("NEEDS_REVIEW requires needs_review_reason")
        return self


class ClaimNode(Provenance):
    id: str
    text: str
    sentence_ids: list[str]
    citation_ids: list[str] = Field(default_factory=list)
    kind: Literal["CLAIM", "EVIDENCE", "ASSUMPTION"] = "CLAIM"


class ClaimEdge(Provenance):
    source_id: str
    target_id: str
    relation: Literal["SUPPORTS", "CONTRADICTS", "DEPENDS_ON"]
    reason: str = Field(min_length=1)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ClaimMap(Provenance):
    paper_id: str
    nodes: list[ClaimNode] = Field(default_factory=list)
    edges: list[ClaimEdge] = Field(default_factory=list)
    status: Literal["COMPLETE", "NEEDS_REVIEW"] = "COMPLETE"
    needs_review_reason: str | None = None


class HiddenTextFinding(Provenance):
    id: str
    kind: Literal["HIDDEN_TEXT", "PROMPT_INJECTION", "SUSPICIOUS_TEXT", "CHECK_INCOMPLETE"]
    page: int | None = Field(default=None, ge=1)
    quote: str
    reason: str = Field(min_length=1)


class ReviewComment(Provenance):
    reviewer: Literal["METHODS", "EVIDENCE", "CLAIMS"]
    severity: Literal["MAJOR", "MINOR"]
    sentence_ids: list[str] = Field(min_length=1)
    quote: str = Field(min_length=1)
    issue: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)
    linked_citation_ids: list[str] = Field(default_factory=list)


class ReviewSummary(Provenance):
    top_fixes: list[str] = Field(default_factory=list)
    comments: list[ReviewComment] = Field(default_factory=list)
    warning: str | None = None


class Report(Contract):
    job_id: UUID
    pipeline_version: str | None = None
    git_sha: str | None = None
    pdf_sha256: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stage_durations: dict[str, float] | None = Field(
        default=None, description="Elapsed seconds per stage, summed over completed attempts."
    )
    paper: Paper | None = None
    existence: list[ExistenceResult] = Field(default_factory=list)
    retractions: list[RetractionResult] = Field(default_factory=list)
    sources: list[SourceDocument] = Field(default_factory=list)
    support: list[SupportResult] = Field(default_factory=list)
    claim_map: ClaimMap | None = None
    hidden_text: list[HiddenTextFinding] = Field(default_factory=list)
    review: ReviewSummary | None = None
    status: Literal["COMPLETE", "NEEDS_REVIEW", "CHECK_INCOMPLETE"]
    reason: str | None = None
