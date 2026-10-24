import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from api.app.resolve.retraction import PostgresRetractions, check_retraction, read_watch_csv
from api.app.resolve.service import ResolveService
from api.tests.test_shared_interfaces import provider
from contracts.schema import ExistenceResult, Reference


class SnapshotPool:
    """Transport fixture for the existing JSONB tables, not a PostgreSQL integration test."""

    def __init__(self):
        self.snapshot = None
        self.rows = {}

    def acquire(self):
        return self

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def execute(self, sql, *args):
        if sql.startswith("DELETE FROM http_cache"):
            self.snapshot = None
        elif sql == "DELETE FROM retraction_watch":
            self.rows.clear()
        elif sql.startswith("INSERT INTO http_cache"):
            self.snapshot = json.loads(args[1])

    async def executemany(self, sql, rows):
        self.rows.update({key: json.loads(payload) for key, payload in rows})

    async def fetchrow(self, sql, key, doi):
        if self.snapshot is None:
            return None
        return {"snapshot": self.snapshot, "records": [self.rows[doi]] if doi in self.rows else []}


CSV = "OriginalPaperDOI,RetractionDOI,RetractionDate,RetractionNature\n"


async def test_empty_or_partial_dataset_never_authorizes_a_clean_result():
    pool = SnapshotPool()
    store = PostgresRetractions(pool)
    assert await store.lookup("10.1234/a") is None
    assert await store.import_csv(CSV + "10.1234/a,,2023-01-01,Retraction\n") == (1, 0)
    assert await store.lookup("10.1234/a") is None
    assert await store.lookup("10.1234/missing") is None


async def test_complete_snapshot_persists_and_all_notices_survive():
    pool = SnapshotPool()
    store = PostgresRetractions(pool)
    data = (
        CSV
        + "10.1234/a,10.1234/n1,2022-01-01,Correction\n"
        + ("10.1234/a,10.1234/n2,2023-01-01,Retraction\n")
    )
    assert await store.import_csv(data, complete=True, fetched_at=datetime.now(UTC)) == (2, 0)
    records = await PostgresRetractions(pool).lookup("10.1234/a")
    assert [r.notice_type for r in records] == ["CORRECTION", "RETRACTION"]
    assert [r.notice_url for r in records] == [
        "https://doi.org/10.1234/n1",
        "https://doi.org/10.1234/n2",
    ]
    assert await store.lookup("10.1234/missing") == []
    assert await store.import_csv(
        CSV + "10.1234/b,,2023-01-01,Retraction\n", complete=True, fetched_at=datetime.now(UTC)
    ) == (
        1,
        0,
    )
    assert await store.lookup("10.1234/a") == []  # replacement removes obsolete rows


@pytest.mark.parametrize("age", [timedelta(days=8), timedelta(days=-1)])
async def test_stale_or_future_snapshot_is_unknown(age):
    pool = SnapshotPool()
    store = PostgresRetractions(pool)
    await store.import_csv(
        CSV + "10.1234/a,,2023-01-01,Retraction\n", complete=True, fetched_at=datetime.now(UTC)
    )
    pool.snapshot["fetched_at"] = (datetime.now(UTC) - age).isoformat()
    assert await store.lookup("10.1234/a") is None
    assert await store.lookup("10.1234/missing") is None


@pytest.mark.parametrize("value", [[], {}, {"version": 99}, None])
async def test_corrupt_snapshot_is_unknown(value):
    pool = SnapshotPool()
    pool.snapshot = value
    assert await PostgresRetractions(pool).lookup("10.1234/a") is None


async def test_bad_complete_import_cannot_replace_a_good_snapshot():
    pool = SnapshotPool()
    store = PostgresRetractions(pool)
    await store.import_csv(
        CSV + "10.1234/a,,2023-01-01,Retraction\n", complete=True, fetched_at=datetime.now(UTC)
    )
    before = pool.snapshot.copy()
    assert await store.import_csv(
        "wrong,header\nx,y", complete=True, fetched_at=datetime.now(UTC)
    ) == (0, 1)
    assert await store.import_csv(CSV, complete=True, fetched_at=datetime.now(UTC)) == (0, 1)
    assert pool.snapshot == before
    await store.import_csv(CSV + "10.1234/b,,2023-01-01,Retraction\n")
    assert await store.lookup("10.1234/a") is None  # partial updates revoke completeness


@pytest.mark.parametrize("stamp", [None, datetime(2020, 1, 1, tzinfo=UTC), datetime(2024, 1, 1)])
async def test_complete_import_requires_an_explicit_current_fetch_time(stamp):
    pool = SnapshotPool()
    store = PostgresRetractions(pool)
    assert await store.import_csv(
        CSV + "10.1234/a,,2023-01-01,Retraction\n", complete=True, fetched_at=stamp
    ) == (0, 1)
    assert pool.snapshot is None and not pool.rows


@pytest.mark.parametrize(
    "notice,status",
    [
        ("Correction", "CORRECTED"),
        ("Expression of Concern", "EXPRESSION_OF_CONCERN"),
        ("Retraction", "RETRACTED"),
    ],
)
async def test_notice_types_and_chronology_reach_the_public_contract(notice, status):
    from api.app.providers.models import Work

    work = Work(
        provider="openalex",
        id="W1",
        doi="10.1234/a",
        title="A real study title",
        authors=["Smith"],
        year=2024,
        is_retracted=False,
    )
    reference = Reference(
        id="b1",
        raw_text=work.title,
        title=work.title,
        authors=work.authors,
        year=work.year,
        doi=work.doi,
    )
    existence = ExistenceResult(
        reference_id="b1", status="VERIFIED", matched_reference=reference, reason="fixture"
    )
    records, rejected = read_watch_csv(CSV + f"10.1234/a,10.1234/n,2023-01-01,{notice}\n")
    assert not rejected
    store = type("Store", (), {"lookup": AsyncMock(return_value=records)})()
    service = ResolveService(None, provider("openalex", [work]), retractions=store)
    result = await service.check_retraction(existence, date(2024, 1, 1))
    assert result.status == status and result.notice_urls == ["https://doi.org/10.1234/n"]
    assert (await service.check_retraction(existence, date(2022, 1, 1))).status == "NONE"
    assert (await service.check_retraction(existence, None)).status == "UNKNOWN"


def test_unknown_notice_types_are_not_guessed():
    assert read_watch_csv(CSV + "10.1234/a,,2023-01-01,Unknown\n") == ([], 1)


def test_unknown_retraction_flag_cannot_be_hidden_by_a_correction():
    from api.app.providers.models import Work

    work = Work(provider="openalex", id="W1", doi="10.1234/a", is_retracted=True)
    records, _ = read_watch_csv(CSV + "10.1234/a,,2023-01-01,Correction\n")
    assert check_retraction(work, date(2024, 1, 1), records).status == "CHECK_INCOMPLETE"


@pytest.mark.parametrize("notice", ["Retraction", "Correction", "Expression of Concern"])
def test_a_dated_flag_requires_a_notice_receipt(notice):
    from api.app.providers.models import Work

    work = Work(provider="openalex", id="W1", doi="10.1234/a", is_retracted=False)
    records, _ = read_watch_csv(CSV + f"10.1234/a,,2023-01-01,{notice}\n")
    result = check_retraction(work, date(2024, 1, 1), records)
    assert result.status == "CHECK_INCOMPLETE" and "receipt" in result.reason
