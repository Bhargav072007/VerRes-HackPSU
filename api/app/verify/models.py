from typing import Literal

from pydantic import Field

from app.ingest.models import Record

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


class Quote(Record):
    passage_id: str
    quote: str = Field(min_length=1)


class Judgment(Record):
    label: Verdict
    reason: str = Field(min_length=1)
    mismatch_types: list[
        Literal[
            "SCOPE",
            "POPULATION",
            "MAGNITUDE",
            "CAUSAL_OVERREACH",
            "HEDGE_DROPPED",
            "DIRECTION",
            "TEMPORAL",
            "METHOD",
            "NOT_IN_SOURCE",
        ]
    ]
    evidence: list[Quote] = Field(max_length=3)
    evidence_strength: Literal["DIRECT", "INDIRECT", "NONE"]


class Finding(Record):
    status: FinalVerdict
    reason: str
    evidence: list[Quote] = Field(default_factory=list)
    evidence_level: Literal["FULL_TEXT", "ABSTRACT", "NONE"]
    model_ids: list[str] = Field(default_factory=list)
    prompt_version: str = "v1"
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
