import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.app import db
from api.app.settings import Settings


@pytest.fixture
def migration_pool():
    connection = AsyncMock()
    connection.transaction = MagicMock()
    connection.transaction.return_value.__aenter__.return_value = connection
    connection.fetchval.return_value = None
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = connection
    return pool, connection


async def test_create_pool_uses_env_settings(monkeypatch):
    factory = AsyncMock()
    monkeypatch.setattr(db.asyncpg, "create_pool", factory)
    settings = Settings(_env_file=None, database_url="postgresql://fixture/db")
    assert await db.create_pool(settings) is factory.return_value
    assert factory.await_args.kwargs["dsn"] == "postgresql://fixture/db"
    assert factory.await_args.kwargs["timeout"] == 5


async def test_migrations_order_and_tracking(migration_pool, migration_directory):
    pool, connection = migration_pool
    await db.run_migrations(pool, migration_directory)
    sql_calls = [call.args[0] for call in connection.execute.await_args_list]
    assert "pg_advisory_xact_lock" in sql_calls[0]
    assert sql_calls[2] == (migration_directory / "001_fixture.sql").read_text()
    assert sql_calls[4] == (migration_directory / "002_fixture.sql").read_text()
    assert connection.fetchval.await_count == 2
    connection.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)


async def test_applied_migrations_skipped(migration_pool, migration_directory):
    pool, connection = migration_pool
    connection.fetchval.side_effect = [
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(migration_directory.glob("*"))
    ]
    await db.run_migrations(pool, migration_directory)
    assert connection.execute.await_count == 2


async def test_changed_migration_rejected(migration_pool, migration_directory):
    pool, connection = migration_pool
    connection.fetchval.return_value = "different-checksum"
    with pytest.raises(RuntimeError, match="Applied migration changed"):
        await db.run_migrations(pool, migration_directory)
    assert connection.execute.await_count == 2
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is RuntimeError


async def test_failed_migration_rolls_back(migration_pool, migration_directory):
    pool, connection = migration_pool
    connection.execute.side_effect = [None, None, RuntimeError("fixture SQL failure")]
    with pytest.raises(RuntimeError, match="fixture SQL failure"):
        await db.run_migrations(pool, migration_directory)
    assert connection.execute.await_count == 3
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is RuntimeError


def test_default_migration_directory_exists():
    assert (db.MIGRATIONS / "001_init.sql").is_file()
