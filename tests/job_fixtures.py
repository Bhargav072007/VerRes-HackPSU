"""Fixture PostgreSQL transport: production repository code runs without a socket."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import asyncpg
import pytest


class FixturePool:
    def __init__(self):
        self.rows = {}
        self.events = []
        self.results = {}
        self.leases = set()
        self.sql = []
        self.lock = asyncio.Lock()
        self.close = AsyncMock()
        self.fail_insert = False
        self.fail_commit = False

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        async with self.lock:
            previous = deepcopy((self.rows, self.events, self.results))
            try:
                yield self
                if self.fail_commit:
                    raise asyncpg.PostgresConnectionError("private commit failure")
            except BaseException:
                self.rows, self.events, self.results = previous
                raise

    async def execute(self, sql, *args):
        self.sql.append(sql)
        if sql.startswith("INSERT INTO jobs"):
            job_id, status, job_input, ip = args
            self.rows[job_id] = {
                "id": job_id,
                "status": status,
                "input": json.loads(job_input),
                "client_ip": ip,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        elif sql.startswith("INSERT INTO job_events"):
            if self.fail_insert:
                raise asyncpg.PostgresConnectionError("private credentials")
            job_id, seq, kind, payload = args
            assert not any(e["job_id"] == job_id and e["seq"] == seq for e in self.events)
            self.events.append({"job_id": job_id, "seq": seq, "type": kind, "payload": payload})
        elif sql.startswith("UPDATE jobs"):
            self.rows[args[0]].update(status=args[1], updated_at=datetime.now(UTC))
        elif sql.startswith("INSERT INTO job_results"):
            assert "ON CONFLICT (job_id, type, row_id) DO UPDATE" in sql
            self.results[tuple(args[:3])] = json.loads(args[3])
        else:
            if "pg_advisory_unlock" in sql:
                self.leases.remove(args[0])
            else:
                assert "pg_advisory_xact_lock(739122)" in sql

    async def fetchrow(self, sql, *args):
        self.sql.append(sql)
        if "FILTER" in sql:
            return {
                "hourly": sum(
                    row["client_ip"] == args[0]
                    and row["created_at"] > datetime.now(UTC) - timedelta(hours=1)
                    for row in self.rows.values()
                ),
                "running": sum(row["status"] == "RUNNING" for row in self.rows.values()),
            }
        row = self.rows.get(args[0])
        if row and "to_jsonb" in sql:
            events = [
                {**e, "payload": json.loads(e["payload"])}
                for e in self.events
                if e["job_id"] == args[0]
            ]
            return {"job": json.dumps(row, default=str), "events": json.dumps(events, default=str)}
        assert "WHERE id = $1" in sql
        return deepcopy(row)

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        if "pg_try_advisory_lock" in sql:
            if args[0] in self.leases:
                return False
            self.leases.add(args[0])
            return True
        if "FOR UPDATE" in sql:
            return self.rows.get(args[0], {}).get("status")
        if "MAX(seq)" in sql:
            return max((e["seq"] for e in self.events if e["job_id"] == args[0]), default=0) + 1
        if "EXISTS" in sql:
            return any(
                e["job_id"] == args[0] and e["type"] == "done" and e["seq"] <= args[1]
                for e in self.events
            )
        assert "count(*)" in sql
        return sum(row["status"] == "RUNNING" for row in self.rows.values())

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        if "status IN" in sql:
            return [
                {"id": row["id"]}
                for row in self.rows.values()
                if row["status"] in ("RUNNING", "QUEUED")
            ]
        job_id, after = args
        assert "ORDER BY seq" in sql
        return deepcopy([e for e in self.events if e["job_id"] == job_id and e["seq"] > after])


@pytest.fixture
def job_pool():
    return FixturePool()
