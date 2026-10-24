import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
from pydantic import TypeAdapter, ValidationError

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


class Jobs:
    """The event journal is the durable source for A2 snapshots and streams."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, client_ip: str, job_input: dict, *, running: bool = False):
        async with self.pool.acquire() as connection, connection.transaction():
            # Shared by admission and QUEUED -> RUNNING transitions across workers.
            await connection.execute("SELECT pg_advisory_xact_lock(739122)")
            counts = await connection.fetchrow(
                "SELECT count(*) FILTER (WHERE client_ip = $1 AND "
                "created_at > now() - interval '1 hour') AS hourly, "
                "count(*) FILTER (WHERE status = 'RUNNING') AS running FROM jobs",
                client_ip,
            )
            if counts["hourly"] >= 5 or counts["running"] >= 3:
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
            return job_id

    async def get(self, job_id: UUID):
        return await self.pool.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)

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
            "jsonb_build_object('job_id', job_id, 'seq', seq, 'type', type, 'payload', payload) "
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
            await connection.execute(
                "UPDATE jobs SET status = $2, updated_at = now() WHERE id = $1", job_id, status
            )
        return event
