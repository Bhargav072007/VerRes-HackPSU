import asyncio
import os
from contextlib import asynccontextmanager
from time import monotonic

import asyncpg
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from starlette.exceptions import HTTPException

from api.app.db import Jobs, create_pool, run_migrations
from api.app.orchestrator import Runner, build_services
from api.app.providers.http import get_client
from api.app.review.runtime import configure_logging
from api.app.routes.exports import router as exports_router
from api.app.routes.health import router
from api.app.routes.jobs import dev_router, error
from api.app.routes.jobs import router as jobs_router
from api.app.routes.shares import router as shares_router
from api.app.routes.status import router as status_router
from api.app.settings import Settings
from api.app.sse import EventBus
from contracts.events import SSEEvent
from contracts.schema import Judgment, Report


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
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
            app.state.event_bus = EventBus(Jobs(app.state.pool))
            app.state.services = build_services(app.state.settings, app.state.pool)
            app.state.runner = Runner(
                app.state.event_bus, app.state.services, app.state.settings, app.state.tasks
            )
            await app.state.runner.recover()
        yield
    finally:
        tasks = list(app.state.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if app.state.services is not None:
            await app.state.services.aclose()
        await get_client("arxiv-intake").aclose()
        if app.state.pool is not None:
            await app.state.pool.close()
        await app.state.grobid_client.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="VerRes", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.state.event_bus = None
    app.state.tasks = set()
    app.state.services = None
    app.state.runner = None
    app.state.started_at = monotonic()
    app.state.demo_fixture = os.getenv("DEMO_FIXTURE", "0") == "1"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list({"http://localhost:3000", app.state.settings.frontend_origin}),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    app.include_router(router)
    app.include_router(jobs_router)
    app.include_router(shares_router)
    app.include_router(exports_router)
    app.include_router(status_router)
    if app.state.settings.env == "dev":
        app.include_router(dev_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exception):
        return error("invalid_request", "Request validation failed.")

    @app.exception_handler(HTTPException)
    async def http_error(request, exception):
        if exception.status_code == 404:
            return JSONResponse(
                {"code": "not_found", "message": "Route not found."}, status_code=404
            )
        return JSONResponse(
            {"code": "invalid_request", "message": "Request could not be parsed."},
            status_code=exception.status_code,
        )

    async def storage_error(request, exception):
        return error("CHECK_INCOMPLETE", "Job storage is unavailable.")

    for exception in (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
        app.add_exception_handler(exception, storage_error)

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
