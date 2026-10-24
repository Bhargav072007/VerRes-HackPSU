import hashlib
from pathlib import Path

import asyncpg

from api.app.settings import Settings

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
