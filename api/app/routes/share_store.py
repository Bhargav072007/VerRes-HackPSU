"""Durable share lifecycle and admission, serialized across API workers."""

import hashlib
import re
import secrets

from api.app.db import JobFailure


class Shares:
    def __init__(self, pool):
        self.pool = pool

    async def create(self, job_id, client_ip: str, days: int):
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 739123))", ip_hash
            )
            if not await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM jobs WHERE id = $1)", job_id
            ):
                return JobFailure(code="job_not_found", message="Job not found.")
            count = await connection.fetchval(
                "SELECT count(*) FROM share_creations WHERE ip_hash = $1 "
                "AND created_at > now() - interval '1 hour'",
                ip_hash,
            )
            if count >= 20:
                return JobFailure(code="rate_limited", message="Share creation limit: 20 per hour.")
            row = await connection.fetchrow(
                "INSERT INTO shares (token, job_id, expires_at) "
                "VALUES ($1, $2, now() + $3 * interval '1 day') RETURNING token, expires_at",
                secrets.token_urlsafe(16),
                job_id,
                days,
            )
            await connection.execute(
                "INSERT INTO share_creations (token, ip_hash) VALUES ($1, $2)",
                row["token"],
                ip_hash,
            )
            return row

    async def access(self, token: str, *, revoke: bool = False):
        if not re.fullmatch(r"[A-Za-z0-9_-]{22}", token):
            return JobFailure(code="share_not_found", message="Share link not found.")
        async with self.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                "SELECT *, expires_at <= now() AS expired FROM shares WHERE token = $1 FOR UPDATE",
                token,
            )
            # The database uses an indexed lookup; verify the bearer secret in constant time.
            matches = secrets.compare_digest(token, row["token"] if row else "0" * 22)
            if row is None or not matches:
                return JobFailure(code="share_not_found", message="Share link not found.")
            if row["revoked_at"] is not None or row["expired"]:
                return JobFailure(
                    code="share_gone",
                    message="Share link has been revoked."
                    if row["revoked_at"]
                    else "Share link has expired.",
                )
            await connection.execute(
                "UPDATE shares SET revoked_at = now() WHERE token = $1"
                if revoke
                else "UPDATE shares SET view_count = view_count + 1 WHERE token = $1",
                token,
            )
            return row["job_id"]
