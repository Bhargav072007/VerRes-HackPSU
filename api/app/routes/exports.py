"""Portable report receipts, with the same privacy boundary as shared views."""

import json
from collections import Counter
from html import escape
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from api.app.routes.jobs import ERRORS, JobSnapshot, snapshot
from api.app.routes.shares import SHARE_ERRORS, SharedSnapshot, shared_snapshot

router = APIRouter()
EXPORT_CONTENT = {
    200: {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/JobSnapshot"}},
            "text/markdown": {"schema": {"type": "string"}},
        }
    }
}


def markdown_receipt(report: dict) -> str:
    counts = Counter(
        row.get("label", row.get("status", "UNKNOWN"))
        for field in ("existence", "retractions", "support")
        for row in report[field]
    )
    lines = [
        "# VerRes receipt",
        "",
        f"Status: {report['status']}",
        "",
        "## Summary counts",
        *[f"- {key}: {value}" for key, value in sorted(counts.items())],
    ]
    if report.get("demo_fixture"):
        lines[2:2] = ["Demo fixture: true (recorded data)", ""]
    lines += [
        "",
        "## Provenance",
        *[
            f"- {key}: {escape(str(report[key])) if report.get(key) is not None else 'Unavailable'}"
            for key in (
                "pipeline_version",
                "git_sha",
                "pdf_sha256",
                "started_at",
                "finished_at",
                "stage_durations",
            )
        ],
        "",
        "## Flagged citations",
    ]
    citations = {row["id"]: row for row in (report.get("paper") or {}).get("citations", [])}
    for field, verdict, healthy in (
        ("existence", "status", {"VERIFIED"}),
        ("retractions", "status", {"NONE"}),
        ("support", "label", {"SUPPORTED"}),
    ):
        for row in report[field]:
            if row[verdict] in healthy:
                continue
            citation = citations.get(row.get("citation_id"), {})
            identifier = row.get("citation_id", row.get("reference_id"))
            lines += [
                "",
                f"### {escape(str(identifier))}: {row[verdict]}",
                escape(citation.get("claim_text", "")),
                "",
                escape(row["reason"]),
            ]
            quotes = [span["quote"] for span in row.get("evidence", [])]
            lines += [
                f"> {escape(quote).replace(chr(10), chr(10) + '> ')}" for quote in quotes
            ] or ["Quote: Unavailable"]
            urls = list(
                dict.fromkeys(
                    filter(
                        None,
                        [
                            row.get("source_url"),
                            *row.get("receipt_urls", []),
                            *row.get("notice_urls", []),
                        ],
                    )
                )
            )
            lines += [f"Source: <{escape(url)}>" for url in urls] or ["Source: Unavailable"]
            lines.append(f"Retrieved at: {row.get('retrieved_at') or 'Unavailable'}")
    return "\n".join(lines) + "\n"


def export_response(report: JobSnapshot | SharedSnapshot | Response, format: str):
    if isinstance(report, JSONResponse) and report.status_code == 200:
        payload = json.loads(report.body)
    elif isinstance(report, Response):
        return report
    else:
        payload = report.model_dump(mode="json")
    if format == "md":
        return Response(markdown_receipt(payload), media_type="text/markdown")
    return JSONResponse(payload)


@router.get(
    "/jobs/{job_id}/export", response_class=Response, responses={**ERRORS, **EXPORT_CONTENT}
)
async def export_job(job_id: UUID, request: Request, format: Literal["json", "md"] = "json"):
    return export_response(await snapshot(job_id, request), format)


@router.get(
    "/shares/{token}/export",
    response_class=Response,
    responses={
        **SHARE_ERRORS,
        200: {
            "content": {
                **EXPORT_CONTENT[200]["content"],
                "application/json": {"schema": {"$ref": "#/components/schemas/SharedSnapshot"}},
            }
        },
    },
)
async def export_share(token: str, request: Request, format: Literal["json", "md"] = "json"):
    return export_response(await shared_snapshot(token, request), format)
