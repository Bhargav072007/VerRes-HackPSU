import asyncio
from typing import Literal

import asyncpg
import httpx
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "CHECK_INCOMPLETE"]
    db: Literal["ok", "CHECK_INCOMPLETE"]
    grobid: Literal["ok", "CHECK_INCOMPLETE"]
    reason: str | None = None


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response) -> HealthResponse:
    db_status = grobid_status = "CHECK_INCOMPLETE"
    pool = request.app.state.pool
    if pool is not None:
        try:
            async with asyncio.timeout(5):
                if await pool.fetchval("SELECT 1") == 1:
                    db_status = "ok"
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError, TimeoutError):
            pass
    try:
        result = await request.app.state.grobid_client.get(
            request.app.state.settings.grobid_url.rstrip("/") + "/api/isalive",
            timeout=5,
        )
        if result.status_code == 200 and result.text.strip().lower() == "true":
            grobid_status = "ok"
    except httpx.HTTPError:
        pass
    healthy = db_status == grobid_status == "ok"
    response.status_code = 200 if healthy else 503
    return HealthResponse(
        status="ok" if healthy else "CHECK_INCOMPLETE",
        db=db_status,
        grobid=grobid_status,
        reason=None if healthy else "Database or GROBID check incomplete",
    )
