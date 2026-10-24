from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import TypeAdapter

from api.app.db import create_pool, run_migrations
from api.app.providers.http import get_client
from api.app.routes.health import router
from api.app.settings import Settings
from contracts.events import SSEEvent
from contracts.schema import Judgment, Report


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = None
    app.state.grobid_client = get_client("grobid")
    try:
        try:
            app.state.pool = await create_pool(app.state.settings)
        except (OSError, asyncpg.PostgresError, TimeoutError):
            # Health remains available and reports CHECK_INCOMPLETE without secrets.
            pass
        if app.state.pool is not None:
            await run_migrations(app.state.pool)
        yield
    finally:
        if app.state.pool is not None:
            await app.state.pool.close()
        await app.state.grobid_client.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="VerRes", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app.state.settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    app.include_router(router)

    def openapi():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            contracts = TypeAdapter(Report | Judgment | SSEEvent).json_schema(
                ref_template="#/components/schemas/{model}"
            )
            schema.setdefault("components", {}).setdefault("schemas", {}).update(
                contracts.pop("$defs")
            )
            schema["components"]["schemas"]["VerResContract"] = contracts
            event_schema = TypeAdapter(SSEEvent).json_schema(
                ref_template="#/components/schemas/{model}"
            )
            event_schema.pop("$defs")
            schema["components"]["schemas"]["SSEEvent"] = event_schema
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
    return app


app = create_app()
