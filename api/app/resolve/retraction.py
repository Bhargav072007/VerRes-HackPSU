import csv
import io
import json
from datetime import date, datetime
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


class RetractionResult(Record):
    status: Literal["RETRACTED", "NOT_RETRACTED", "CHECK_INCOMPLETE"]
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
        if (
            "RetractionNature" in row
            and (row["RetractionNature"] or "").strip().lower() != "retraction"
        ):
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
                notice_url=(
                    "https://doi.org/" + quote(normalize_doi(row.get("RetractionDOI")), safe="/")
                )
                if normalize_doi(row.get("RetractionDOI"))
                else None,
            )
        )
    return rows, rejected


class PostgresRetractions:
    def __init__(self, pool):
        self.pool = pool

    async def import_csv(self, data: str) -> tuple[int, int]:
        rows, rejected = read_watch_csv(data)
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.executemany(
                "INSERT INTO retraction_watch(doi,payload) VALUES($1,$2::jsonb) "
                "ON CONFLICT(doi) DO UPDATE SET payload=EXCLUDED.payload,updated_at=now()",
                [(r.doi, r.model_dump_json()) for r in rows],
            )
        return len(rows), rejected

    async def lookup(self, doi: str) -> list[RetractionRecord] | None:
        try:
            rows = await self.pool.fetch(
                "SELECT payload FROM retraction_watch WHERE doi=$1",
                normalize_doi(doi),
            )
        except (PostgresError, OSError):
            return None
        try:
            return [
                RetractionRecord.model_validate_json(
                    r["payload"] if isinstance(r["payload"], str) else json.dumps(r["payload"])
                )
                for r in rows
            ]
        except (ValueError, TypeError, KeyError):
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
    if any(r.retracted and r.retracted < citing_date for r in matched):
        return RetractionResult(
            status="RETRACTED", reason="retraction predates the citing paper", records=matched
        )
    if any(r.retracted is None for r in matched) or (work.is_retracted and not matched):
        return RetractionResult(
            status="CHECK_INCOMPLETE", reason="retraction date is unavailable", records=matched
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
