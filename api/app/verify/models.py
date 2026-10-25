from typing import Literal

from pydantic import Field

from api.app.ingest.models import Record
from contracts.schema import EvidenceSpan as Quote
from contracts.schema import Judgment as Judgment

Verdict = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED"]
FinalVerdict = Literal[
    "SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NEEDS_REVIEW"
]
Function = Literal["SPECIFIC_CLAIM", "METHOD_OR_TOOL", "BACKGROUND", "CONTRAST"]


class FunctionItem(Record):
    citation_id: str
    function: Function


class Classification(Record):
    items: list[FunctionItem]


class AtomicClaim(Record):
    text: str = Field(min_length=1)
    subject_or_population: str = Field(min_length=1)
    exposure_or_intervention: str | None
    outcome: str = Field(min_length=1)
    direction: Literal["increase", "decrease", "no effect", "n.a."]
    magnitude: str | None
    relation: Literal["causal", "associative", "descriptive"]
    hedge: Literal["definite", "likely", "possible"]
    scope_or_time: str | None


class ClaimSplit(Record):
    ambiguous: bool
    claims: list[AtomicClaim] = Field(min_length=1, max_length=3)


class Passage(Record):
    id: str
    text: str


class Finding(Record):
    status: FinalVerdict
    reason: str
    evidence: list[Quote] = Field(default_factory=list)
    evidence_level: Literal["FULL_TEXT", "ABSTRACT", "NONE"]
    evidence_strength: Literal["DIRECT", "INDIRECT", "INSUFFICIENT"] = "INSUFFICIENT"
    model_ids: list[str] = Field(default_factory=list)
    prompt_version: str = "v3"
    source_work_id: str | None = None
    source_origin: str | None = None
    passages: list[Passage] = Field(default_factory=list)
    mismatch_types: list[str] = Field(default_factory=list)


class CitationVerification(Record):
    citation_id: str
    finding: Finding
    claims: list[AtomicClaim] = Field(default_factory=list)
    claim_findings: list[Finding] = Field(default_factory=list)
    citation_function: Function | None = None
