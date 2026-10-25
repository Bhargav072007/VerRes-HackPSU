import hashlib
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
from pydantic import TypeAdapter, ValidationError

from api.app import version
from api.app.settings import Settings
from contracts.events import SSEEvent
from contracts.schema import Contract

MIGRATIONS = Path(__file__).resolve().parents[2] / "infra" / "migrations"


async def create_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=settings.database_url.get_secret_value(),
        min_size=1,
        max_size=5,
        timeout=5,
        command_timeout=10,
    )


async def run_migrations(pool: asyncpg.Pool, directory: Path = MIGRATIONS) -> None:
    async with pool.acquire() as connection, connection.transaction():
        # Serialize concurrent API startups; all DDL and tracking commit together.
        await connection.execute("SELECT pg_advisory_xact_lock(739121)")
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name text PRIMARY KEY, sha256 text NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in sorted(directory.glob("*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            previous = await connection.fetchval(
                "SELECT sha256 FROM schema_migrations WHERE name = $1", path.name
            )
            if previous is not None:
                if previous != checksum:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue
            await connection.execute(sql)
            await connection.execute(
                "INSERT INTO schema_migrations (name, sha256) VALUES ($1, $2)",
                path.name,
                checksum,
            )


class JobFailure(Contract):
    code: str
    message: str


EVENTS = TypeAdapter(SSEEvent)


def cache_key(job_input):
    """The intake route normalizes identifiers before they reach the repository."""
    if "sha256" in job_input:
        return job_input["sha256"]
    for kind in ("arxiv_id", "doi"):
        if kind in job_input:
            return hashlib.sha256(f"{kind}:{job_input[kind]}".encode()).hexdigest()
    return None


class Jobs:
    """The event journal is the durable source for A2 snapshots and streams."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(
        self,
        client_ip: str,
        job_input: dict,
        *,
        running: bool = False,
        exempt_hourly: bool = False,
        fresh: bool = False,
        demo_fixture: bool = False,
    ):
        async with self.pool.acquire() as connection, connection.transaction():
            # Shared by admission and QUEUED -> RUNNING transitions across workers.
            await connection.execute("SELECT pg_advisory_xact_lock(739122)")
            key = cache_key(job_input)
            cached = None
            if key and not fresh and not demo_fixture:
                cached = await connection.fetchrow(
                    "SELECT id, status FROM jobs j WHERE cache_key = $1 AND pipeline_version = $2 "
                    "AND NOT demo_fixture AND status IN ('COMPLETE', 'NEEDS_REVIEW') "
                    "AND EXISTS (SELECT 1 FROM job_events e "
                    "WHERE e.job_id = j.id AND type = 'done') "
                    "AND NOT EXISTS (SELECT 1 FROM job_events e WHERE e.job_id = j.id "
                    "AND (payload->>'status' = 'CHECK_INCOMPLETE' "
                    "OR payload->>'kind' = 'CHECK_INCOMPLETE')) "
                    "ORDER BY updated_at DESC LIMIT 1",
                    key,
                    version.PIPELINE_VERSION,
                )
            counts = await connection.fetchrow(
                "SELECT count(*) FILTER (WHERE client_ip = $1 AND replay_of IS NULL AND "
                "created_at > now() - interval '1 hour') AS hourly, "
                "count(*) FILTER (WHERE status = 'RUNNING') AS running FROM jobs",
                client_ip,
            )
            if (not cached and not exempt_hourly and counts["hourly"] >= 5) or (
                running and counts["running"] >= 3
            ):
                return JobFailure(
                    code="rate_limited", message="Job limit reached; try again later."
                )
            job_id = uuid4()
            await connection.execute(
                "INSERT INTO jobs (id, status, input, client_ip) VALUES ($1, $2, $3::jsonb, $4)",
                job_id,
                "RUNNING" if running else "QUEUED",
                json.dumps(job_input),
                client_ip,
            )
            await connection.execute(
                "UPDATE jobs SET cache_key = $2, pipeline_version = $3, demo_fixture = $4 "
                "WHERE id = $1",
                job_id,
                key,
                version.PIPELINE_VERSION,
                demo_fixture,
            )
            if cached:
                await connection.execute(
                    "INSERT INTO job_events (job_id, seq, type, payload, created_at) "
                    "SELECT $1, seq, type, CASE WHEN type = 'done' "
                    "THEN jsonb_set(payload, '{job_id}', to_jsonb($1::uuid::text)) "
                    "ELSE payload END, created_at FROM job_events WHERE job_id = $2 ORDER BY seq",
                    job_id,
                    cached["id"],
                )
                await connection.execute(
                    "INSERT INTO job_results (job_id, type, row_id, payload) "
                    "SELECT $1, type, row_id, payload FROM job_results WHERE job_id = $2",
                    job_id,
                    cached["id"],
                )
                await connection.execute(
                    "UPDATE jobs SET status = $2, replay_of = $3, updated_at = now() WHERE id = $1",
                    job_id,
                    cached["status"],
                    cached["id"],
                )
            return job_id

    async def metrics(self):
        return dict(
            await self.pool.fetchrow(
                "SELECT count(*) FILTER (WHERE created_at > now() - interval '1 hour') "
                "AS jobs_last_hour, (avg(extract(epoch FROM (updated_at - created_at))) "
                "FILTER (WHERE "
                "created_at > now() - interval '1 hour' AND status NOT IN ('QUEUED', 'RUNNING')) "
                ")::float8 AS avg_duration_seconds FROM jobs"
            )
        )

    async def llm_spend(self):
        row = await self.pool.fetchrow(
            "SELECT coalesce(sum(cost_usd), 0)::float8 AS spend_usd, "
            "count(*) FILTER (WHERE cost_usd IS NULL) AS unknown_calls FROM llm_usage "
            "WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
        )
        return dict(row)

    async def record_spend(self, job_id, cost):
        await self.pool.execute(
            "INSERT INTO llm_usage (id, job_id, cost_usd) VALUES ($1, $2, $3)",
            uuid4(),
            UUID(str(job_id)) if job_id is not None else None,
            Decimal(str(cost)) if cost is not None else None,
        )

    async def get(self, job_id: UUID):
        return await self.pool.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)

    async def unfinished(self):
        return await self.pool.fetch(
            "SELECT id FROM jobs WHERE status IN ('RUNNING', 'QUEUED') "
            "ORDER BY (status = 'RUNNING') DESC, created_at"
        )

    @asynccontextmanager
    async def lease(self, job_id):
        # Session lock prevents two API workers from recovering the same job.
        async with self.pool.acquire() as connection:
            locked = await connection.fetchval(
                "SELECT pg_try_advisory_lock(hashtextextended($1, 0))", str(job_id)
            )
            try:
                yield locked
            finally:
                if locked:
                    await connection.execute(
                        "SELECT pg_advisory_unlock(hashtextextended($1, 0))", str(job_id)
                    )

    async def read_events(self, job_id: UUID, after: int):
        rows = await self.pool.fetch(
            "SELECT job_id, seq, type, payload FROM job_events "
            "WHERE job_id = $1 AND seq > $2 ORDER BY seq",
            job_id,
            after,
        )
        return [
            EVENTS.validate_python({**dict(row), "payload": json.loads(row["payload"])})
            for row in rows
        ]

    async def finished(self, job_id: UUID, cursor: int):
        return await self.pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM job_events "
            "WHERE job_id = $1 AND type = 'done' AND seq <= $2)",
            job_id,
            cursor,
        )

    async def snapshot(self, job_id: UUID):
        # One statement gives a consistent job row + journal, including concurrent emits.
        row = await self.pool.fetchrow(
            "SELECT to_jsonb(jobs) AS job, COALESCE((SELECT jsonb_agg("
            "jsonb_build_object('job_id', job_id, 'seq', seq, 'type', type, 'payload', payload, "
            "'created_at', created_at) "
            "ORDER BY seq) FROM job_events WHERE job_id = jobs.id), '[]'::jsonb) AS events "
            "FROM jobs WHERE id = $1",
            job_id,
        )
        return {key: json.loads(row[key]) for key in ("job", "events")} if row else None

    async def append(self, job_id: UUID, event_type: str, payload: dict):
        async with self.pool.acquire() as connection, connection.transaction():
            # Lock ordering is identical to create; sequence and status commit together.
            await connection.execute("SELECT pg_advisory_xact_lock(739122)")
            status = await connection.fetchval(
                "SELECT status FROM jobs WHERE id = $1 FOR UPDATE", job_id
            )
            if status is None:
                return JobFailure(code="job_not_found", message="Job not found.")
            if status not in ("QUEUED", "RUNNING"):
                return JobFailure(code="CHECK_INCOMPLETE", message="Job has already finished.")
            seq = await connection.fetchval(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM job_events WHERE job_id = $1", job_id
            )
            try:
                event = EVENTS.validate_python(
                    {"job_id": job_id, "seq": seq, "type": event_type, "payload": payload}
                )
            except ValidationError:
                return JobFailure(
                    code="CHECK_INCOMPLETE", message="Event failed contract validation."
                )
            if event.type == "done" and event.payload.job_id != job_id:
                return JobFailure(code="CHECK_INCOMPLETE", message="Report belongs to another job.")
            if status == "QUEUED" and event.type == "stage" and event.payload.status == "STARTED":
                running = await connection.fetchval(
                    "SELECT count(*) FROM jobs WHERE status = 'RUNNING'"
                )
                if running >= 3:
                    return JobFailure(
                        code="rate_limited", message="Three jobs are already running."
                    )
                status = "RUNNING"
            if event.type == "done":
                status = event.payload.status
            await connection.execute(
                "INSERT INTO job_events (job_id, seq, type, payload) "
                "VALUES ($1, $2, $3, $4::jsonb)",
                job_id,
                seq,
                event.type,
                event.payload.model_dump_json(),
            )
            if event.type not in ("stage", "error", "done"):
                payload = event.payload.model_dump(mode="json")
                row_id = next(
                    (
                        payload[key]
                        for key in ("reference_id", "citation_id", "id", "paper_id")
                        if key in payload
                    ),
                    payload.get("reviewer", event.type),
                )
                if event.type == "review":
                    identity = [
                        payload["reviewer"],
                        sorted(payload["sentence_ids"]),
                        payload["quote"],
                        payload["issue"],
                    ]
                    row_id = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                await connection.execute(
                    "INSERT INTO job_results (job_id, type, row_id, payload) "
                    "VALUES ($1, $2, $3, $4::jsonb) "
                    "ON CONFLICT (job_id, type, row_id) DO UPDATE SET payload = EXCLUDED.payload",
                    job_id,
                    event.type,
                    row_id,
                    event.payload.model_dump_json(),
                )
            await connection.execute(
                "UPDATE jobs SET status = $2, updated_at = now() WHERE id = $1", job_id, status
            )
        return event
