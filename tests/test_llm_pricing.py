import json
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from api.app.db import Jobs
from api.app.providers.http import Policy
from api.app.review.runtime import DEFAULT_PRICES, ResilientGateway, model_cost, model_prices
from tests.conftest import FIXTURES


@pytest.fixture
def usage_response(monkeypatch):
    monkeypatch.delenv("MODEL_PRICES", raising=False)
    return json.loads((FIXTURES / "review/usage.json").read_text())


@pytest.mark.parametrize(
    "model,cost,uncached_cost",
    [
        ("gpt-4.1-mini", 0.0021, 0.0024),
        ("gpt-4.1", 0.0105, 0.012),
        ("gpt-4.1-nano", 0.000525, 0.0006),
    ],
)
@pytest.mark.parametrize("suffix", ["", "-2025-04-14"])
def test_default_prices_and_cached_snapshot_usage(
    usage_response, model, cost, uncached_cost, suffix
):
    usage_response["model"] = model + suffix
    assert model_cost(usage_response) == (pytest.approx(cost), False)
    usage_response["usage"].pop("prompt_tokens_details")
    assert model_cost(usage_response) == (pytest.approx(uncached_cost), False)


def test_model_prices_merge_and_exact_snapshot_override(usage_response, monkeypatch):
    monkeypatch.setenv(
        "MODEL_PRICES", '{"gpt-4.1-mini": [1, 2], "gpt-4.1-mini-2025-04-14": [3, 4]}'
    )
    assert model_prices()["gpt-4.1"] == DEFAULT_PRICES["gpt-4.1"]
    assert model_cost(usage_response) == (0.00325, False)
    usage_response["model"] += "-2025-04-14"
    usage_response["usage"].pop("prompt_tokens_details")
    assert model_cost(usage_response) == (0.01, False)


@pytest.mark.parametrize(
    "value", ["bad JSON", "[]", '{"x": [-1, 2]}', '{"x": [true, 2]}', '{"x": [NaN, 2]}']
)
def test_invalid_prices_fall_back_without_exposing_configuration(
    usage_response, monkeypatch, caplog, value
):
    monkeypatch.setenv("MODEL_PRICES", value)
    assert model_prices() == DEFAULT_PRICES
    assert "Invalid MODEL_PRICES" in caplog.text
    assert value not in caplog.text


@pytest.mark.parametrize("model", ["unknown-model", "gpt-4.1-mini-new", None])
def test_unknown_model_conservative_rates_without_cache_discount(
    usage_response, monkeypatch, model
):
    monkeypatch.setenv("MODEL_PRICES", '{"expensive-input": [10, 1], "expensive-output": [1, 20]}')
    usage_response["model"] = model
    assert model_cost(usage_response) == (0.04, True)


def test_request_model_fallback(usage_response):
    usage_response.pop("model")
    assert model_cost(usage_response, request_model="gpt-4.1-mini") == (0.0021, False)


@pytest.mark.parametrize("cached", [-1, True, 2001, "1000"])
def test_invalid_cached_usage_is_unknown(usage_response, cached):
    usage_response["usage"]["prompt_tokens_details"]["cached_tokens"] = cached
    assert model_cost(usage_response) == (None, True)


async def test_priced_call_is_durable_and_cache_hit_is_not_rebilled(
    usage_response, job_pool, respx_mock
):
    jobs = Jobs(job_pool)
    route = respx_mock.get("https://model.example/complete").respond(200, json=usage_response)
    async with ResilientGateway(
        {"review": Policy("https://model.example", 100, 1, 1)}, jobs=jobs
    ) as gateway:
        assert (await gateway.request("review", "/complete", ttl=60)).status == 200
        assert (await gateway.request("review", "/complete", ttl=60)).cached
    assert route.call_count == 1 and len(job_pool.usage) == 1
    assert job_pool.usage[0][2:] == (Decimal("0.0021"), False)
    spend = await jobs.llm_spend()
    assert spend["spend_usd"] == spend["known_spend_usd"] == 0.0021
    assert spend["estimated_calls"] == spend["unknown_calls"] == 0
    query = job_pool.sql[-1]
    assert "WHERE estimated" in query and "cost_usd IS NULL AND NOT legacy_unknown" in query
    assert "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'" in query


async def test_accounting_storage_failure_blocks_model_calls(
    usage_response, job_pool, respx_mock, monkeypatch
):
    jobs = Jobs(job_pool)
    monkeypatch.setattr(jobs, "llm_spend", AsyncMock(side_effect=OSError("fixture storage down")))
    route = respx_mock.post("https://model.example/complete").respond(200, json=usage_response)
    async with ResilientGateway(
        {"review": Policy("https://model.example", 100, 1, 1)}, jobs=jobs
    ) as gateway:
        result = await gateway.request("review", "/complete", method="POST")
    assert "storage unavailable" in result.error and not route.called
