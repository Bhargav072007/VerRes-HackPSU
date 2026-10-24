"""Cache adapters. Lane A owns creation/migration of the documented SQL tables."""

import json
import time
from typing import Protocol

from app.providers.models import HTTPResult


class Cache(Protocol):
    async def get(self, key: str) -> HTTPResult | None: ...

    async def put(self, key: str, value: HTTPResult, ttl: int) -> None: ...


class MemoryCache:
    """Explicit ephemeral development cache; not a production persistence substitute."""

    def __init__(self, clock=time.time):
        self.entries: dict[str, tuple[float, HTTPResult]] = {}
        self.clock = clock

    async def get(self, key: str) -> HTTPResult | None:
        entry = self.entries.get(key)
        if entry and entry[0] > self.clock():
            return entry[1].model_copy(update={"cached": True})
        self.entries.pop(key, None)
        return None

    async def put(self, key: str, value: HTTPResult, ttl: int) -> None:
        self.entries[key] = (self.clock() + ttl, value)


class PostgresCache:
    def __init__(self, pool):
        self.pool = pool

    async def get(self, key: str) -> HTTPResult | None:
        row = await self.pool.fetchrow(
            "SELECT status, body, headers FROM http_cache "
            "WHERE cache_key=$1 AND expires_at > now()",
            key,
        )
        if not row:
            return None
        headers = row["headers"]
        return HTTPResult(
            status=row["status"],
            content=bytes(row["body"]),
            headers=json.loads(headers) if isinstance(headers, str) else headers,
            cached=True,
        )

    async def put(self, key: str, value: HTTPResult, ttl: int) -> None:
        await self.pool.execute(
            "INSERT INTO http_cache(cache_key,status,body,headers,expires_at) "
            "VALUES($1,$2,$3,$4::jsonb,now()+$5 * interval '1 second') "
            "ON CONFLICT(cache_key) DO UPDATE SET status=EXCLUDED.status,body=EXCLUDED.body,"
            "headers=EXCLUDED.headers,expires_at=EXCLUDED.expires_at",
            key,
            value.status,
            value.content,
            json.dumps(value.headers),
            ttl,
        )
