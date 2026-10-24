"""Typed SSE payloads. seq is monotonically increasing within each job."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from contracts.schema import (
    ClaimMap,
    Contract,
    ExistenceResult,
    HiddenTextFinding,
    Paper,
    Report,
    RetractionResult,
    ReviewComment,
    ReviewSummary,
    SourceDocument,
    SupportResult,
)


class StagePayload(Contract):
    stage: str
    status: Literal["STARTED", "COMPLETED", "CHECK_INCOMPLETE"]
    reason: str | None = None


class ErrorPayload(Contract):
    code: str
    reason: str
    retryable: bool = False


class Event(Contract):
    job_id: UUID
    seq: int = Field(ge=1)


class StageEvent(Event):
    type: Literal["stage"] = "stage"
    payload: StagePayload


class PaperEvent(Event):
    type: Literal["paper"] = "paper"
    payload: Paper


class ExistenceEvent(Event):
    type: Literal["existence"] = "existence"
    payload: ExistenceResult


class RetractionEvent(Event):
    type: Literal["retraction"] = "retraction"
    payload: RetractionResult


class SourceEvent(Event):
    type: Literal["source"] = "source"
    payload: SourceDocument


class SupportEvent(Event):
    type: Literal["support"] = "support"
    payload: SupportResult


class ClaimMapEvent(Event):
    type: Literal["claim_map"] = "claim_map"
    payload: ClaimMap


class HiddenTextEvent(Event):
    type: Literal["hidden_text"] = "hidden_text"
    payload: HiddenTextFinding


class ReviewEvent(Event):
    type: Literal["review"] = "review"
    payload: ReviewComment


class ReviewSummaryEvent(Event):
    type: Literal["review_summary"] = "review_summary"
    payload: ReviewSummary


class DoneEvent(Event):
    type: Literal["done"] = "done"
    payload: Report


class ErrorEvent(Event):
    type: Literal["error"] = "error"
    payload: ErrorPayload


SSEEvent = Annotated[
    StageEvent
    | PaperEvent
    | ExistenceEvent
    | RetractionEvent
    | SourceEvent
    | SupportEvent
    | ClaimMapEvent
    | HiddenTextEvent
    | ReviewEvent
    | ReviewSummaryEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]
