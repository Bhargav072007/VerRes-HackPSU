"""Operational metadata only; never serialize settings, provider URLs or keys."""

from time import monotonic

import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.app import version

router = APIRouter()


@router.get("/status")
async def status(request: Request):
    state = request.app.state
    result = {
        "uptime_seconds": round(monotonic() - state.started_at, 3),
        "git_sha": version.GIT_SHA,
        "pipeline_version": version.PIPELINE_VERSION,
        "demo_fixture": state.demo_fixture,
        "jobs_last_hour": None,
        "avg_duration_seconds": None,
        "providers": {
            name: {"state": "UNCONFIGURED"} for name in ("crossref", "openalex", "arxiv", "model")
        },
        "llm": {
            "spend_usd": None,
            "known_spend_usd": None,
            "unknown_calls": None,
            "daily_budget_usd": state.settings.llm_daily_budget,
            "day_timezone": "UTC",
        },
        "status": "ok",
        "reason": None,
    }
    services = state.services
    result["providers"]["model"]["reason"] = (
        services.model_unconfigured_reason if services else "model not configured"
    )
    if services:
        for gateway in (getattr(services.backend, "gateway", None), services.model_gateway):
            if gateway and hasattr(gateway, "breaker_states"):
                result["providers"].update(gateway.breaker_states())
    result["models"] = {
        role: {
            "model_id": model.model_id if model else None,
            "vendor": model.vendor if model else None,
            "family": model.family if model else None,
            "state": result["providers"]["model"]["state"] if model else "UNCONFIGURED",
        }
        for role, model in (
            ("primary", services.primary_model if services else None),
            ("adjudicator", services.adjudicator_model if services else None),
        )
    }
    try:
        if state.event_bus is None:
            raise OSError()
        result.update(await state.event_bus.jobs.metrics())
        spend = await state.event_bus.jobs.llm_spend()
        accounting_incomplete = bool(
            services and services.model_gateway and services.model_gateway.accounting_incomplete
        )
        result["llm"].update(
            spend_usd=None
            if spend["unknown_calls"] or accounting_incomplete
            else spend["spend_usd"],
            known_spend_usd=spend["spend_usd"],
            unknown_calls=spend["unknown_calls"],
            accounting_incomplete=accounting_incomplete or bool(spend["unknown_calls"]),
        )
        if result["llm"]["accounting_incomplete"]:
            result.update(status="CHECK_INCOMPLETE", reason="LLM cost accounting incomplete.")
    except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError, TimeoutError):
        result.update(status="CHECK_INCOMPLETE", reason="Operational storage unavailable.")
    return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503)
