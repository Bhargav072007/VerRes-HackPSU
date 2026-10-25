from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field

from api.app.db import JobFailure
from api.app.routes.jobs import ERRORS, JobSnapshot, error, snapshot
from api.app.routes.share_store import Shares
from contracts.schema import (
    Contract,
    Paper,
    Report,
    ReviewComment,
    Sentence,
    SourceDocument,
    SourcePassage,
)

router = APIRouter()
SHARE_ERRORS = {**ERRORS, 410: {"model": JobFailure}}


class ShareCreated(Contract):
    token: str
    url: str
    expires_at: datetime


class SharedPaper(Paper):
    sentences: list[Sentence] = Field(default_factory=list, exclude=True)


class SharedSource(SourceDocument):
    passages: list[SourcePassage] = Field(default_factory=list, exclude=True)


class SharedSnapshot(Report):
    status: Literal["QUEUED", "RUNNING", "COMPLETE", "NEEDS_REVIEW", "CHECK_INCOMPLETE"]
    paper: SharedPaper | None = None
    sources: list[SharedSource] = Field(default_factory=list)
    review_comments: list[ReviewComment] = Field(default_factory=list)
    shared: Literal[True] = True


def share_error(failure: JobFailure):
    if failure.code in ("share_not_found", "share_gone"):
        return JSONResponse(
            failure.model_dump(), status_code=410 if failure.code == "share_gone" else 404
        )
    return error(failure.code, failure.message)


def public_snapshot(report: JobSnapshot) -> SharedSnapshot:
    # Explicit field projection excludes job input/IP, errors, stages and the SSE journal.
    return SharedSnapshot.model_validate(
        report.model_dump(include=set(SharedSnapshot.model_fields) - {"shared"})
    )


@router.post("/jobs/{job_id}/share", response_model=ShareCreated, responses=SHARE_ERRORS)
async def create_share(job_id: UUID, request: Request, days: int = Query(default=30, ge=1, le=90)):
    bus = request.app.state.event_bus
    if bus is None:
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")
    result = await Shares(bus.jobs.pool).create(
        job_id, request.client.host if request.client else "unknown", days
    )
    if isinstance(result, JobFailure):
        return share_error(result)
    return ShareCreated(
        **dict(result), url=str(request.url_for("shared_snapshot", token=result["token"]))
    )


@router.delete("/shares/{token}", status_code=204, responses=SHARE_ERRORS)
async def revoke_share(token: str, request: Request):
    bus = request.app.state.event_bus
    if bus is None:
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")
    result = await Shares(bus.jobs.pool).access(token, revoke=True)
    return share_error(result) if isinstance(result, JobFailure) else Response(status_code=204)


@router.get("/shares/{token}", response_model=SharedSnapshot, responses=SHARE_ERRORS)
async def shared_snapshot(token: str, request: Request):
    bus = request.app.state.event_bus
    if bus is None:
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")
    result = await Shares(bus.jobs.pool).access(token)
    if isinstance(result, JobFailure):
        return share_error(result)
    report = await snapshot(result, request)
    if isinstance(report, Response):
        return report
    return public_snapshot(report)
