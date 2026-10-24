import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.parse import quote

from asyncpg import PostgresError
from pydantic import Field

from api.app.ingest.models import Record
from api.app.providers.metadata import normalize_doi
from api.app.providers.models import Work


class RetractionRecord(Record):
    doi: str
    retracted: date | None
    provenance: str
    notice_url: str | None = None
    notice_type: Literal["RETRACTION", "CORRECTION", "EXPRESSION_OF_CONCERN"] = "RETRACTION"


class RetractionResult(Record):
    status: Literal[
        "RETRACTED", "NOT_RETRACTED", "CHECK_INCOMPLETE", "CORRECTED", "EXPRESSION_OF_CONCERN"
    ]
    reason: str
    records: list[RetractionRecord] = Field(default_factory=list)


def parse_date(value: str) -> date | None:
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None


def read_watch_csv(data: str) -> tuple[list[RetractionRecord], int]:
    rows, rejected = [], 0
    reader = csv.DictReader(io.StringIO(data.lstrip("\ufeff")))
    if not reader.fieldnames or not {"OriginalPaperDOI", "RetractionDate"} <= set(
        reader.fieldnames
    ):
        return [], 1
    for row in reader:
        nature = (row.get("RetractionNature", "retraction") or "").strip().lower()
        notice_type = {
            "retraction": "RETRACTION",
            "correction": "CORRECTION",
            "expression of concern": "EXPRESSION_OF_CONCERN",
        }.get(nature)
        if notice_type is None:
            rejected += 1
            continue
        doi = normalize_doi(row.get("OriginalPaperDOI"))
        if not doi:
            rejected += 1
            continue
        rows.append(
            RetractionRecord(
                doi=doi,
                retracted=parse_date(row.get("RetractionDate") or ""),
                provenance="Retraction Watch CSV",
                notice_type=notice_type,
                notice_url=(
                    "https://doi.org/" + quote(normalize_doi(row.get("RetractionDOI")), safe="/")
                )
                if normalize_doi(row.get("RetractionDOI"))
                else None,
            )
        )
    return rows, rejected


class PostgresRetractions:
    SNAPSHOT_KEY = "retraction-watch:snapshot:v1"
    MAX_AGE = timedelta(days=7)

    def __init__(self, pool):
        self.pool = pool

    async def import_csv(
        self, data: str, *, complete: bool = False, fetched_at: datetime | None = None
    ) -> tuple[int, int]:
        """Only an explicitly complete, valid snapshot authorizes negative checks.

        Freshness metadata uses the existing expiring JSONB cache table; no migration
        or new public schema is required. Snapshot replacement and marker commit together.
        """
        rows, rejected = read_watch_csv(data)
        now = datetime.now(UTC)
        if complete and (
            rejected
            or not rows
            or fetched_at is None
            or fetched_at.tzinfo is None
            or not timedelta(0) <= now - fetched_at <= self.MAX_AGE
        ):
            return 0, max(rejected, 1)
        grouped = defaultdict(list)
        for record in rows:
            grouped[record.doi].append(record.model_dump(mode="json"))
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(739123)")
            await connection.execute("DELETE FROM http_cache WHERE cache_key=$1", self.SNAPSHOT_KEY)
            if complete:
                await connection.execute("DELETE FROM retraction_watch")
            await connection.executemany(
                "INSERT INTO retraction_watch(doi,payload) VALUES($1,$2::jsonb) "
                "ON CONFLICT(doi) DO UPDATE SET payload=EXCLUDED.payload,updated_at=now()",
                [(doi, json.dumps(notices)) for doi, notices in grouped.items()],
            )
            if complete:
                await connection.execute(
                    "INSERT INTO http_cache(cache_key,payload,expires_at) VALUES($1,$2::jsonb,$3)",
                    self.SNAPSHOT_KEY,
                    json.dumps(
                        {
                            "version": 1,
                            "complete": True,
                            "rows": len(rows),
                            "sha256": hashlib.sha256(data.encode()).hexdigest(),
                            "fetched_at": fetched_at.isoformat(),
                        }
                    ),
                    fetched_at + self.MAX_AGE,
                )
        return len(rows), rejected

    async def lookup(self, doi: str) -> list[RetractionRecord] | None:
        try:
            # One statement reads a consistent marker + records, including concurrent imports.
            row = await self.pool.fetchrow(
                "SELECT payload AS snapshot, (SELECT COALESCE(jsonb_agg(payload), '[]'::jsonb) "
                "FROM retraction_watch WHERE doi=$2) AS records FROM http_cache "
                "WHERE cache_key=$1 AND expires_at > now()",
                self.SNAPSHOT_KEY,
                normalize_doi(doi),
            )
        except (PostgresError, OSError):
            return None
        try:
            if not row:
                return None
            snapshot = row["snapshot"]
            snapshot = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
            stamp = datetime.fromisoformat(snapshot["fetched_at"])
            if (
                snapshot.get("version") != 1
                or snapshot.get("complete") is not True
                or type(snapshot.get("rows")) is not int
                or snapshot["rows"] < 1
                or not isinstance(snapshot.get("sha256"), str)
                or len(snapshot["sha256"]) != 64
                or stamp.tzinfo is None
                or not timedelta(0) <= datetime.now(UTC) - stamp <= self.MAX_AGE
            ):
                return None
            payloads = row["records"]
            payloads = json.loads(payloads) if isinstance(payloads, str) else payloads
            records = [
                RetractionRecord.model_validate_json(json.dumps(record))
                for payload in payloads
                for record in (payload if isinstance(payload, list) else [payload])
            ]
            if any(record.doi != normalize_doi(doi) for record in records):
                return None
            return records
        except (ValueError, TypeError, KeyError, AttributeError):
            return None


def check_retraction(
    work: Work, citing_date: date | None, records: list[RetractionRecord] | None
) -> RetractionResult:
    doi = normalize_doi(work.doi)
    matched = [r for r in records or [] if doi and normalize_doi(r.doi) == doi]
    if not citing_date:
        return RetractionResult(
            status="CHECK_INCOMPLETE", reason="citing paper date is unavailable", records=matched
        )
    retractions = [r for r in matched if r.notice_type == "RETRACTION"]
    prior_retractions = [r for r in retractions if r.retracted and r.retracted < citing_date]
    if prior_retractions:
        if not any(r.notice_url for r in prior_retractions):
            return RetractionResult(
                status="CHECK_INCOMPLETE",
                reason="dated retraction notice receipt is unavailable",
                records=matched,
            )
        return RetractionResult(
            status="RETRACTED", reason="retraction predates the citing paper", records=matched
        )
    if any(r.retracted is None for r in matched) or (work.is_retracted and not retractions):
        return RetractionResult(
            status="CHECK_INCOMPLETE", reason="retraction date is unavailable", records=matched
        )
    for kind, status in (
        ("EXPRESSION_OF_CONCERN", "EXPRESSION_OF_CONCERN"),
        ("CORRECTION", "CORRECTED"),
    ):
        if any(r.notice_type == kind and r.retracted < citing_date for r in matched):
            if not any(
                r.notice_type == kind and r.retracted < citing_date and r.notice_url
                for r in matched
            ):
                return RetractionResult(
                    status="CHECK_INCOMPLETE",
                    reason="dated notice receipt is unavailable",
                    records=matched,
                )
            return RetractionResult(
                status=status, reason="dated notice predates the citing paper", records=matched
            )
    if records is None or work.is_retracted is None or not doi:
        return RetractionResult(
            status="CHECK_INCOMPLETE", reason="retraction sources are incomplete", records=matched
        )
    return RetractionResult(
        status="NOT_RETRACTED",
        reason="no known retraction predating the citing paper",
        records=matched,
    )
