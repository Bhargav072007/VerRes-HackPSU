"""Lane A's gateway configuration and safe operational context.

All network I/O still runs through providers.http.Gateway, including its retries,
rate limits, HTTP cache and pinned source downloads.
"""

import json
import logging
import math
import os
from contextvars import ContextVar
from datetime import UTC, datetime

from api.app.providers.http import Circuit, Gateway

job_context = ContextVar("job_id", default=None)
stage_context = ContextVar("stage", default="server")
provider_issues = ContextVar("provider_issues", default=None)
logger = logging.getLogger(__name__)
TIMEOUTS = {"crossref": 10, "openalex": 10, "arxiv": 20, "model": 60}


def provider_group(name):
    return {
        "crossref_single": "crossref",
        "crossref_query": "crossref",
        "arxiv-intake": "arxiv",
        "review": "model",
    }.get(name, name)


class DemoCircuit(Circuit):
    def record(self, failed, status, now):
        failed = failed or (status is not None and status >= 400 and status != 404)
        super().record(failed, status, now)
        if failed and self.failures >= 3:
            self.open_until = now + 60


class ResilientGateway(Gateway):
    def __init__(self, *args, jobs=None, **kwargs):
        super().__init__(*args, **kwargs)
        groups = {provider_group(name): DemoCircuit() for name in self.policies}
        self.circuits = {name: groups[provider_group(name)] for name in self.policies}
        self.jobs = jobs
        self.accounting_incomplete = False

    async def _request(self, provider, url, method, ttl, timeout, **kwargs):  # noqa: ASYNC109
        group = provider_group(provider)
        cap = TIMEOUTS.get(group, 20)
        # Accounting uncertainty must not discard independently verified evidence.
        if group == "model" and self.jobs:
            try:
                spend = await self.jobs.llm_spend()
                if spend["spend_usd"] >= self.daily_budget_usd:
                    from api.app.providers.models import HTTPResult

                    self.note_issue(group, "daily budget exhausted")
                    return HTTPResult(error="model daily budget exhausted")
            except Exception:
                self.accounting_incomplete = True
            result = await self.perform(provider, url, method, ttl, min(timeout, cap), kwargs)
            if not result.cached and not result.error and result.status == 200:
                try:
                    cost = model_cost(result.json())
                except (ValueError, TypeError):
                    cost = None
                try:
                    await self.jobs.record_spend(job_context.get(), cost)
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
            provider_group(name): {
                "state": "OPEN"
                if circuit.open_until > self.clock()
                else ("HALF_OPEN" if circuit.open_until else "CLOSED"),
                "consecutive_failures": circuit.failures,
                "retry_after_seconds": max(0, round(circuit.open_until - self.clock(), 2)),
                "timeout_seconds": TIMEOUTS.get(provider_group(name), 20),
            }
            for name, circuit in self.circuits.items()
        }


def model_cost(payload):
    """No implicit model pricing: unknown usage/prices stays unknown in /status."""
    try:
        usage = payload["usage"]
        rates = [
            float(os.environ[name])
            for name in ("LLM_INPUT_USD_PER_MILLION", "LLM_OUTPUT_USD_PER_MILLION")
        ]
        tokens = [usage["prompt_tokens"], usage["completion_tokens"]]
        if any(type(n) is not int or n < 0 for n in tokens):
            return None
        if any(not math.isfinite(rate) or rate < 0 for rate in rates):
            return None
        return sum(n * rate / 1_000_000 for n, rate in zip(tokens, rates, strict=True))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


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
