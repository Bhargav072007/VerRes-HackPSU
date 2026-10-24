"""Internal extraction details. Public lane interfaces return contracts.schema models."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ParsedReference(Record):
    id: str
    raw: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv: str | None = None
    pmid: str | None = None
    kind: str = "unknown"


class ParsedSentence(Record):
    id: str
    text: str
    section: str


class ParsedCitation(Record):
    id: str
    reference_id: str
    sentence_id: str
    text: str
    marker: str
    section: str
    reference_title: str | None = None
    reference_raw: str | None = None
    previous: str | None = None
    next: str | None = None


class ParsedPaper(Record):
    title: str | None = None
    published: date | None = None
    sentences: list[ParsedSentence] = Field(default_factory=list)
    references: list[ParsedReference] = Field(default_factory=list)
    citations: list[ParsedCitation] = Field(default_factory=list)


class ParseResult(Record):
    status: Literal["FULL", "PARTIAL", "FAILED"]
    paper: ParsedPaper = Field(default_factory=ParsedPaper)
    reasons: list[str] = Field(default_factory=list)
    parser: str


class HiddenSpan(Record):
    page: int
    text: str
    categories: list[str]
    bbox: tuple[float, float, float, float]
    reason: str


class HiddenScan(Record):
    status: Literal["COMPLETE", "CHECK_INCOMPLETE"]
    spans: list[HiddenSpan] = Field(default_factory=list)
    reason: str | None = None
