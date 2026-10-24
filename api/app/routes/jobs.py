import asyncio
import hashlib
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, Self
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse
from pydantic import Field, ValidationError, model_validator
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from api.app.db import JobFailure
from api.app.routes.demo import run_fake_job
from contracts.events import ErrorPayload, SSEEvent, StagePayload
from contracts.schema import Contract, Report, ReviewComment

PDF_LIMIT = 25 * 1024 * 1024
router = APIRouter()
dev_router = APIRouter()


class Identifier(Contract):
    arxiv_id: str | None = Field(default=None, min_length=1, max_length=256)
    doi: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        if len(self.model_fields_set) != 1 or (self.arxiv_id is None) == (self.doi is None):
            raise ValueError("Provide exactly one of arxiv_id or doi")
        return self


class Accepted(Contract):
    job_id: UUID


class JobRow(Contract):
    id: UUID
    status: Literal["QUEUED", "RUNNING", "COMPLETE", "NEEDS_REVIEW", "CHECK_INCOMPLETE"]
    input: dict[str, str]
    client_ip: str
    created_at: datetime
    updated_at: datetime


class JobSnapshot(Report):
    status: Literal["QUEUED", "RUNNING", "COMPLETE", "NEEDS_REVIEW", "CHECK_INCOMPLETE"]
    job: JobRow
    events: list[SSEEvent]
    stages: list[StagePayload] = Field(default_factory=list)
    errors: list[ErrorPayload] = Field(default_factory=list)
    review_comments: list[ReviewComment] = Field(default_factory=list)


def error(code, message):
    status = {
        "rate_limited": 429,
        "job_not_found": 404,
        "pdf_too_large": 413,
        "CHECK_INCOMPLETE": 503,
    }.get(code, 400)
    return JSONResponse(JobFailure(code=code, message=message).model_dump(), status_code=status)


def save_pdf(data: bytes, data_dir: Path):
    if len(data) > PDF_LIMIT:
        return JobFailure(code="pdf_too_large", message="PDF must be at most 25 MB.")
    if not data.startswith(b"%PDF-"):
        return JobFailure(code="pdf_invalid", message="Upload must start with %PDF-.")
    try:
        pages = len(PdfReader(BytesIO(data), strict=True).pages)
        if not pages:
            return JobFailure(code="pdf_invalid", message="PDF has no pages.")
        if pages > 80:
            return JobFailure(code="too_many_pages", message="PDF must have at most 80 pages.")
    except Exception:
        return JobFailure(code="pdf_invalid", message="PDF could not be read.")
    digest = hashlib.sha256(data).hexdigest()
    uploads = data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=uploads, delete=False) as temporary:
        path = Path(temporary.name)
        try:
            temporary.write(data)
            temporary.close()
            os.replace(path, uploads / f"{digest}.pdf")
        finally:
            path.unlink(missing_ok=True)
    return {"sha256": digest}


ERRORS = {status: {"model": JobFailure} for status in (400, 404, 413, 429, 503)}
INTAKE_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    **Identifier.model_json_schema(),
                    "oneOf": [{"required": ["arxiv_id"]}, {"required": ["doi"]}],
                }
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "additionalProperties": False,
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            },
        },
    }
}


@router.post(
    "/jobs", status_code=202, response_model=Accepted, responses=ERRORS, openapi_extra=INTAKE_BODY
)
async def create_job(request: Request):
    bus = request.app.state.event_bus
    if bus is None:
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type == "multipart/form-data":
        async with request.form(max_files=1, max_fields=0) as form:
            file = form.get("file")
            if len(form) != 1 or not isinstance(file, UploadFile):
                return error("invalid_request", "Provide a PDF in the multipart field file.")
            job_input = await run_in_threadpool(
                save_pdf, await file.read(PDF_LIMIT + 1), request.app.state.settings.data_dir
            )
    elif media_type == "application/json":
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return error("invalid_request", "Identifier request is too large.")
        try:
            job_input = Identifier.model_validate_json(body).model_dump(exclude_none=True)
        except ValidationError:
            return error("invalid_request", "Provide exactly one nonempty arxiv_id or doi.")
    else:
        return error("invalid_request", "Use multipart/form-data or application/json.")
    if isinstance(job_input, JobFailure):
        return error(job_input.code, job_input.message)
    result = await bus.jobs.create(request.client.host if request.client else "unknown", job_input)
    return (
        error(result.code, result.message)
        if isinstance(result, JobFailure)
        else Accepted(job_id=result)
    )


@router.get("/jobs/{job_id}", response_model=JobSnapshot, responses=ERRORS)
async def snapshot(job_id: UUID, request: Request):
    bus = request.app.state.event_bus
    if bus is None:
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")
    state = await bus.jobs.snapshot(job_id)
    if state is None:
        return error("job_not_found", "Job not found.")
    result = {**state, "job_id": job_id, "status": state["job"]["status"]}
    arrays = {
        "existence": "existence",
        "retraction": "retractions",
        "source": "sources",
        "support": "support",
        "hidden_text": "hidden_text",
        "stage": "stages",
        "error": "errors",
        "review": "review_comments",
    }
    for event in state["events"]:
        kind, payload = event["type"], event["payload"]
        if kind in arrays:
            result.setdefault(arrays[kind], []).append(payload)
        elif kind == "done":
            # A minimal failure report must not erase receipts emitted earlier.
            for field, value in payload.items():
                if field in ("job_id", "status", "reason") or field not in result:
                    result[field] = value
        else:
            result[{"review_summary": "review"}.get(kind, kind)] = payload
    return JobSnapshot.model_validate(result)


@router.get(
    "/jobs/{job_id}/events",
    response_class=Response,
    responses={**ERRORS, 200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def events(job_id: UUID, request: Request):
    bus = request.app.state.event_bus
    if bus is None:
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")
    if await bus.jobs.get(job_id) is None:
        return error("job_not_found", "Job not found.")
    value = request.headers.get("last-event-id", "0")
    if not value.isascii() or not value.isdecimal() or len(value) > 19 or int(value) > 2**63 - 1:
        return error("invalid_request", "Last-Event-ID must be a nonnegative sequence number.")
    # Construct the native SSE response after preflight so failures remain JSON.
    return EventSourceResponse(
        bus.stream(job_id, int(value)),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@dev_router.post("/dev/fake-job", status_code=202, response_model=Accepted, responses=ERRORS)
async def fake_job(request: Request):
    bus = request.app.state.event_bus
    if bus is None:
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")
    job_id = await bus.jobs.create(
        request.client.host if request.client else "unknown", {"demo": "fixture"}, running=True
    )
    if isinstance(job_id, JobFailure):
        return error(job_id.code, job_id.message)
    task = asyncio.create_task(run_fake_job(bus, job_id))
    request.app.state.tasks.add(task)
    task.add_done_callback(request.app.state.tasks.discard)
    return Accepted(job_id=job_id)
