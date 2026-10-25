"""Fixture PostgreSQL transport: production repository code runs without a socket."""

import asyncio
import json
import math
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
        self.shares = {}
        self.share_creations = {}
        self.sql = []
        self.lock = asyncio.Lock()
        self.close = AsyncMock()
        self.fail_insert = False
        self.fail_commit = False
        self.usage = []
        self.legacy_unknown = set()

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        async with self.lock:
            previous = deepcopy(
                (self.rows, self.events, self.results, self.shares, self.share_creations)
            )
            try:
                yield self
                if self.fail_commit:
                    raise asyncpg.PostgresConnectionError("private commit failure")
            except BaseException:
                self.rows, self.events, self.results, self.shares, self.share_creations = previous
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
        elif sql.startswith("INSERT INTO job_events") and "SELECT $1" in sql:
            for event in list(self.events):
                if event["job_id"] == args[1]:
                    payload = json.loads(event["payload"])
                    if event["type"] == "done":
                        payload["job_id"] = str(args[0])
                    self.events.append({**event, "job_id": args[0], "payload": json.dumps(payload)})
        elif sql.startswith("INSERT INTO job_events"):
            if self.fail_insert:
                raise asyncpg.PostgresConnectionError("private credentials")
            job_id, seq, kind, payload = args
            assert not any(e["job_id"] == job_id and e["seq"] == seq for e in self.events)
            self.events.append(
                {
                    "job_id": job_id,
                    "seq": seq,
                    "type": kind,
                    "payload": payload,
                    "created_at": datetime.now(UTC),
                }
            )
        elif sql.startswith("INSERT INTO share_creations"):
            self.share_creations[args[0]] = {"ip_hash": args[1], "created_at": datetime.now(UTC)}
        elif sql.startswith("UPDATE shares"):
            if "revoked_at" in sql:
                self.shares[args[0]]["revoked_at"] = datetime.now(UTC)
            else:
                self.shares[args[0]]["view_count"] += 1
        elif sql.startswith("UPDATE jobs SET cache_key"):
            self.rows[args[0]].update(
                cache_key=args[1], pipeline_version=args[2], demo_fixture=args[3]
            )
        elif sql.startswith("UPDATE jobs"):
            self.rows[args[0]].update(status=args[1], updated_at=datetime.now(UTC))
            if "replay_of" in sql:
                self.rows[args[0]]["replay_of"] = args[2]
        elif sql.startswith("INSERT INTO job_results") and "SELECT $1" in sql:
            for (job_id, kind, row_id), payload in list(self.results.items()):
                if job_id == args[1]:
                    self.results[(args[0], kind, row_id)] = deepcopy(payload)
        elif sql.startswith("INSERT INTO job_results"):
            assert "ON CONFLICT (job_id, type, row_id) DO UPDATE" in sql
            self.results[tuple(args[:3])] = json.loads(args[3])
        elif sql.startswith("INSERT INTO llm_usage"):
            self.usage.append(args)
        else:
            if "pg_advisory_unlock" in sql:
                self.leases.remove(args[0])
            else:
                assert "pg_advisory_xact_lock" in sql

    async def fetchrow(self, sql, *args):
        self.sql.append(sql)
        if sql.startswith("INSERT INTO shares"):
            token, job_id, days = args
            assert token not in self.shares and job_id in self.rows
            now = datetime.now(UTC)
            self.shares[token] = {
                "token": token,
                "job_id": job_id,
                "created_at": now,
                "expires_at": now + timedelta(days=days),
                "revoked_at": None,
                "view_count": 0,
            }
            return {key: self.shares[token][key] for key in ("token", "expires_at")}
        if "FROM shares" in sql:
            row = self.shares.get(args[0])
            return {**row, "expired": row["expires_at"] <= datetime.now(UTC)} if row else None
        if "FROM llm_usage" in sql:
            return {
                "spend_usd": float(sum(r[2] for r in self.usage if r[2] is not None)),
                "known_spend_usd": float(
                    sum(r[2] for r in self.usage if r[2] is not None and not r[3])
                ),
                "estimated_spend_usd": float(
                    sum(r[2] for r in self.usage if r[2] is not None and r[3])
                ),
                "estimated_calls": sum(r[3] for r in self.usage),
                "unknown_calls": sum(r[2] is None for r in self.usage),
                "legacy_unknown_calls": sum(
                    r[2] is None and r[0] in self.legacy_unknown for r in self.usage
                ),
                "unaccounted_calls": sum(
                    r[2] is None and r[0] not in self.legacy_unknown for r in self.usage
                ),
            }
        if "AS jobs_last_hour" in sql:
            recent = [
                r
                for r in self.rows.values()
                if r["created_at"] > datetime.now(UTC) - timedelta(hours=1)
            ]
            durations = [
                (r["updated_at"] - r["created_at"]).total_seconds()
                for r in recent
                if r["status"] not in ("RUNNING", "QUEUED")
            ]
            return {
                "jobs_last_hour": len(recent),
                "avg_duration_seconds": sum(durations) / len(durations) if durations else None,
            }
        if "FROM jobs j WHERE cache_key" in sql:
            for row in sorted(self.rows.values(), key=lambda r: r["updated_at"], reverse=True):
                events = [e for e in self.events if e["job_id"] == row["id"]]
                if (
                    row.get("cache_key") == args[0]
                    and row.get("pipeline_version") == args[1]
                    and not row.get("demo_fixture")
                    and row["status"] in ("COMPLETE", "NEEDS_REVIEW")
                    and any(e["type"] == "done" for e in events)
                    and not any(
                        (
                            json.loads(e["payload"]).get("status") == "CHECK_INCOMPLETE"
                            or json.loads(e["payload"]).get("kind") == "CHECK_INCOMPLETE"
                        )
                        for e in events
                    )
                ):
                    return deepcopy(row)
            return None
        if "FILTER" in sql:
            return {
                "hourly": sum(
                    row["client_ip"] == args[0]
                    and not row.get("replay_of")
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
        if "SELECT GREATEST(1, CEIL" in sql:
            now = datetime.now(UTC)
            recent = sorted(
                (
                    row["created_at"]
                    for row in self.rows.values()
                    if row["client_ip"] == args[0]
                    and not row.get("replay_of")
                    and row["created_at"] > now - timedelta(hours=1)
                ),
                reverse=True,
            )
            return max(1, math.ceil((recent[args[1]] + timedelta(hours=1) - now).total_seconds()))
        if "SELECT EXISTS (SELECT 1 FROM jobs" in sql:
            return args[0] in self.rows
        if "FROM share_creations" in sql:
            return sum(
                row["ip_hash"] == args[0]
                and row["created_at"] > datetime.now(UTC) - timedelta(hours=1)
                for row in self.share_creations.values()
            )
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
        return deepcopy(
            [
                {key: value for key, value in e.items() if key != "created_at"}
                for e in self.events
                if e["job_id"] == job_id and e["seq"] > after
            ]
        )


@pytest.fixture
def job_pool():
    return FixturePool()
