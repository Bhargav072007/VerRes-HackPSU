"""Cache adapters. Lane A owns creation/migration of the documented SQL tables."""

import base64
import binascii
import json
import time
from typing import Protocol

from api.app.providers.models import HTTPResult


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
            "SELECT payload FROM http_cache WHERE cache_key=$1 AND expires_at > now()",
            key,
        )
        if not row:
            return None
        try:
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return HTTPResult(
                status=payload["status"],
                content=base64.b64decode(payload["body_base64"], validate=True),
                headers=payload["headers"],
                cached=True,
            )
        except (KeyError, TypeError, ValueError, binascii.Error):
            # An incompatible/invalid cache entry is a miss, never a citation verdict.
            return None

    async def put(self, key: str, value: HTTPResult, ttl: int) -> None:
        await self.pool.execute(
            "INSERT INTO http_cache(cache_key,payload,expires_at) "
            "VALUES($1,$2::jsonb,now()+$3 * interval '1 second') "
            "ON CONFLICT(cache_key) DO UPDATE SET payload=EXCLUDED.payload,"
            "expires_at=EXCLUDED.expires_at",
            key,
            json.dumps(
                {
                    "status": value.status,
                    "body_base64": base64.b64encode(value.content).decode(),
                    "headers": value.headers,
                }
            ),
            ttl,
        )
