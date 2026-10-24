"""PROVISIONAL Partner B types; adapt explicitly to Lane A contracts when supplied."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Reference(Record):
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


class Sentence(Record):
    id: str
    text: str
    section: str


class Citation(Record):
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


class Paper(Record):
    title: str | None = None
    published: date | None = None
    sentences: list[Sentence] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class ParseResult(Record):
    status: Literal["FULL", "PARTIAL", "FAILED"]
    paper: Paper = Field(default_factory=Paper)
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
