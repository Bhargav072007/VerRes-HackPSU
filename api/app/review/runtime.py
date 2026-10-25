"""Lane A's gateway configuration and safe operational context.

All network I/O still runs through providers.http.Gateway, including its retries,
rate limits, HTTP cache and pinned source downloads.
"""

import json
import logging
import math
import os
import re
from contextvars import ContextVar
from datetime import UTC, datetime

from api.app.providers.http import Circuit, Gateway
from api.app.providers.models import HTTPResult

job_context = ContextVar("job_id", default=None)
stage_context = ContextVar("stage", default="server")
provider_issues = ContextVar("provider_issues", default=None)
logger = logging.getLogger(__name__)
TIMEOUTS = {"crossref": 10, "openalex": 10, "arxiv": 20, "model": 60}
DEFAULT_PRICES = {
    "gpt-4.1-mini": [0.40, 1.60],
    "gpt-4.1": [2.00, 8.00],
    "gpt-4.1-nano": [0.10, 0.40],
    # Google standard paid text rates, checked 2026-10-25; override as rates change.
    "gemini-3.6-flash": [1.50, 7.50],
}


def provider_group(name):
    return {
        "crossref_single": "crossref",
        "crossref_query": "crossref",
        "arxiv-intake": "arxiv",
        "review": "model",
        "gemini": "model",
    }.get(name, name)


class DemoCircuit(Circuit):
    def record(self, failed, status, now):
        failed = failed or (status is not None and status >= 400 and status != 404)
        super().record(failed, status, now)
        if failed and self.failures >= 3:
            self.open_until = now + 60


class ResilientGateway(Gateway):
    def __init__(self, *args, jobs=None, price_overrides=None, **kwargs):
        super().__init__(*args, **kwargs)
        groups = {
            ("gemini" if name == "gemini" else provider_group(name)): DemoCircuit()
            for name in self.policies
        }
        self.circuits = {
            name: groups["gemini" if name == "gemini" else provider_group(name)]
            for name in self.policies
        }
        self.jobs = jobs
        self.accounting_incomplete = False
        self.model_prices = model_prices(price_overrides)

    async def _request(self, provider, url, method, ttl, timeout, **kwargs):  # noqa: ASYNC109
        group = provider_group(provider)
        cap = TIMEOUTS.get(group, 20)
        # Accounting uncertainty must not discard independently verified evidence.
        if group == "model" and self.jobs:
            try:
                spend = await self.jobs.llm_spend()
                if self.accounting_incomplete or spend["unaccounted_calls"]:
                    self.note_issue(group, "usage unavailable; budget cannot be enforced")
                    return HTTPResult(error="model usage unavailable; budget cannot be enforced")
                if spend["spend_usd"] >= self.daily_budget_usd:
                    self.note_issue(group, "daily budget exhausted")
                    return HTTPResult(error="model daily budget exhausted")
            except Exception:
                self.accounting_incomplete = True
                self.note_issue(group, "accounting storage unavailable")
                return HTTPResult(error="model accounting storage unavailable")
            result = await self.perform(provider, url, method, ttl, min(timeout, cap), kwargs)
            if not result.cached and not result.error and result.status == 200:
                try:
                    cost, estimated = model_cost(
                        result.json(),
                        prices=self.model_prices,
                        request_model=kwargs.get("json", {}).get("model"),
                    )
                except (ValueError, TypeError):
                    cost, estimated = None, True
                try:
                    await self.jobs.record_spend(job_context.get(), cost, estimated=estimated)
                except Exception:
                    self.accounting_incomplete = True
                    logger.warning("model cost accounting incomplete")
            return result
        return await self.perform(provider, url, method, ttl, min(timeout, cap), kwargs)

    async def perform(self, provider, url, method, ttl, deadline, kwargs):
        result = await super()._request(provider, url, method, ttl, deadline, **kwargs)
        if result.error or result.status is None or (result.status >= 400 and result.status != 404):
            group = provider_group(provider)
            circuit = self.circuits[provider]
            reason = (
                "circuit open; retry after 60s"
                if circuit.open_until > self.clock()
                else f"request incomplete (HTTP {result.status or 'unavailable'})"
            )
            self.note_issue(group, reason)
            return result.model_copy(update={"error": f"{group}: {reason}"})
        return result

    def note_issue(self, group, reason):
        issues = provider_issues.get()
        if issues is not None:
            issues.append(f"{group}: {reason}")
        logger.warning("provider incomplete", extra={"provider": group, "reason": reason})

    def breaker_states(self):
        return {
            ("gemini" if name == "gemini" else provider_group(name)): {
                "state": "OPEN"
                if circuit.open_until > self.clock()
                else ("HALF_OPEN" if circuit.open_until else "CLOSED"),
                "consecutive_failures": circuit.failures,
                "retry_after_seconds": max(0, round(circuit.open_until - self.clock(), 2)),
                "timeout_seconds": TIMEOUTS.get(provider_group(name), 20),
            }
            for name, circuit in self.circuits.items()
        }


def model_prices(value=None):
    """Merge valid per-million price pairs without trusting external configuration."""
    prices = dict(DEFAULT_PRICES)
    try:
        overrides = json.loads(value if value is not None else os.getenv("MODEL_PRICES", "{}"))
        if not isinstance(overrides, dict):
            raise ValueError("expected a model-price mapping")
        for model, rates in overrides.items():
            if (
                not model.strip()
                or not isinstance(rates, list)
                or len(rates) != 2
                or any(
                    type(rate) not in (int, float) or not math.isfinite(rate) or rate < 0
                    for rate in rates
                )
            ):
                raise ValueError("invalid model-price pair")
        prices.update(overrides)
    except (ValueError, TypeError, OverflowError):
        logger.warning("Invalid MODEL_PRICES; using built-in model prices.")
    return prices


def model_cost(payload, *, prices=None, request_model=None):
    """Return USD and an estimate flag; never invent missing token usage."""
    try:
        prices = model_prices() if prices is None else prices
        model = payload.get("model") or request_model
        if isinstance(model, str):
            model = model.removeprefix("models/")
        matched = next(
            (
                name
                for name in sorted(prices, key=len, reverse=True)
                if isinstance(model, str)
                and (model == name or re.fullmatch(re.escape(name) + r"-\d{4}-\d{2}-\d{2}", model))
            ),
            None,
        )
        rates = prices[matched] if matched else [max(p[i] for p in prices.values()) for i in (0, 1)]
        usage = payload["usage"]
        prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        if (
            any(type(n) is not int or n < 0 for n in (prompt, completion, cached))
            or cached > prompt
        ):
            return None, True
        # Only the documented GPT-4.1 family gets a 75% cached-input discount.
        discount = 0.75 if matched in {"gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"} else 0
        cost = ((prompt - cached * discount) * rates[0] + completion * rates[1]) / 1_000_000
        estimated = matched is None or isinstance(model, str) and model.startswith("gemini-")
        return (cost, estimated) if math.isfinite(cost) else (None, True)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None, True


class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "job_id": getattr(record, "job_id", job_context.get()),
            "stage": getattr(record, "stage", stage_context.get()),
            "message": record.getMessage(),
        }
        for key in ("duration_seconds", "provider", "reason"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


def configure_logging():
    formatter = JSONFormatter()
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            if not handler.__class__.__module__.startswith("_pytest"):
                handler.setFormatter(formatter)
    root.setLevel(logging.INFO)
    # Client URLs can contain provider credentials in query strings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
