"""Derive report metadata from receipts; unavailable provenance stays null."""

from datetime import datetime

from api.app.version import GIT_SHA, PIPELINE_VERSION


def report_provenance(result: dict, state: dict) -> None:
    result["pipeline_version"] = result.get("pipeline_version") or PIPELINE_VERSION
    result["git_sha"] = result.get("git_sha") or GIT_SHA
    result["pdf_sha256"] = state["job"].get("input", {}).get("sha256")
    starts, durations = {}, {}
    for event in state["events"]:
        timestamp = event.get("created_at")
        if timestamp is None:
            continue  # Old fixture journals may have no event timestamps.
        at = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        payload = event["payload"]
        if event["type"] == "done":
            result["finished_at"] = at
        if event["type"] != "stage":
            continue
        stage = payload["stage"]
        if payload["status"] == "STARTED":
            if result.get("started_at") is None:
                result["started_at"] = at
            starts[stage] = at
        elif stage in starts:
            elapsed = (at - starts.pop(stage)).total_seconds()
            if elapsed >= 0:
                durations[stage] = durations.get(stage, 0) + elapsed
    if durations:
        result["stage_durations"] = durations
    for field, alias in (("existence", "receipt_urls"), ("retractions", "notice_urls")):
        for row in result.get(field, []):
            row["source_url"] = row.get("source_url") or next(iter(row.get(alias, [])), None)
    for row in result.get("sources", []):
        row["source_url"] = row.get("source_url") or row.get("url")
    sources = {row["reference_id"]: row for row in result.get("sources", [])}
    citations = {row["id"]: row for row in (result.get("paper") or {}).get("citations", [])}
    for row in result.get("support", []):
        source = sources.get(citations.get(row["citation_id"], {}).get("reference_id"), {})
        for item in (row, *row.get("evidence", [])):
            for field in ("source_url", "source_type", "retrieved_at", "evidence_level"):
                if item.get(field) is None:
                    item[field] = row.get(field) or source.get(field)
