import json
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

from api.app import main
from api.app.db import Jobs
from api.app.review.runtime import job_context, provider_issues
from api.app.settings import Settings
from api.app.verify.model import ModelFailure
from contracts.schema import Report
from tests.conftest import FIXTURES


@pytest.fixture
def model_case(respx_mock):
    report = Report(
        job_id=UUID(int=1),
        status="COMPLETE",
        **json.loads((FIXTURES / "pipeline/paper1.json").read_text()),
    )
    for sentence in report.paper.sentences:
        sentence.section = "Results"
    responses = json.loads((FIXTURES / "review/support_model.json").read_text())
    responses.update(json.loads((FIXTURES / "review/panel.json").read_text()))
    responses["judge"] = report.support[0].model_dump(
        exclude={"citation_id", "needs_review_reason", "adjudicated"}
    )
    responses["claim_map"] = report.claim_map.model_dump()

    def respond(request):
        payload = json.loads(request.content)
        task = payload["response_format"]["json_schema"]["name"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(responses[task])},
                    }
                ],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 2000},
            },
        )

    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(side_effect=respond)
    return report, route


@pytest.fixture
async def wired_app(monkeypatch, job_pool, request, tmp_path):
    config = getattr(request, "param", {})
    monkeypatch.delenv("STUBS")
    monkeypatch.setenv("MODEL_PRIMARY", config.get("primary", "fixture-primary"))
    monkeypatch.setenv("REVIEW_MODEL", config.get("legacy", "fixture-legacy"))
    monkeypatch.setenv("LLM_INPUT_USD_PER_MILLION", "1")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_MILLION", "2")
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    app = main.create_app(
        Settings(
            _env_file=None,
            env="test",
            data_dir=tmp_path,
            openai_api_key=config.get("key", "fixture-private-key"),
            anthropic_api_key="sk-ant-api-fixture-private-key",
            llm_daily_budget=0.05,
            frontend_origin=" https://first.example/// , , https://second.example/ , ",
        )
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield app, client
    assert all(c.is_closed for c in app.state.services.backend.gateway.clients.values())
    if app.state.services.model_gateway:
        assert all(c.is_closed for c in app.state.services.model_gateway.clients.values())


@pytest.mark.parametrize(
    "wired_app,expected_model",
    [
        ({"primary": " fixture-primary "}, "fixture-primary"),
        ({"primary": "", "legacy": " fixture-legacy "}, "fixture-legacy"),
        ({"primary": "   ", "legacy": "fixture-legacy"}, "fixture-legacy"),
    ],
    indirect=["wired_app"],
)
async def test_startup_wires_support_graph_panel_and_accounting(
    wired_app, model_case, caplog, expected_model
):
    app, client = wired_app
    report, route = model_case
    services = app.state.services
    model = services.review.model
    assert model.model_id == expected_model
    assert model.gateway is services.model_gateway
    assert services.backend.verify.primary is services.backend.graph.model is model
    assert services.backend.verify.adjudicator is None
    startup = "\n".join(record.getMessage() for record in caplog.get_records("setup"))
    assert startup.count(f"model configured: openai/{model.model_id}, adjudicator: none") == 1
    status = (await client.get("/status")).json()
    assert status["providers"]["model"]["state"] == "CLOSED"
    job_id = await Jobs(app.state.pool).create("model-test", {"sha256": "a" * 64})
    token = job_context.set(str(job_id))
    try:
        support = await services.backend.verify.verify_citation(
            report.paper.citations[0], report.sources[0]
        )
        graph = await services.backend.graph.build_claim_map(report.paper)
        review = await services.review.run_review_panel(report.paper, report.support)
    finally:
        job_context.reset(token)
    assert support.label == "SUPPORTED" and support.evidence[0].quote in (
        report.sources[0].passages[0].text
    )
    assert graph.status == "COMPLETE" and len(review.comments) == 3
    assert len(review.top_fixes) == 3
    tasks = []
    for call in route.calls:
        payload = json.loads(call.request.content)
        tasks.append(payload["response_format"]["json_schema"]["name"])
        assert payload["model"] == model.model_id
        assert call.request.extensions["timeout"]["read"] == 60
    assert set(tasks) == {
        "classify",
        "split",
        "judge",
        "claim_map",
        "r1_methods",
        "r2_evidence",
        "r3_claims",
        "chair",
    }
    assert len(app.state.pool.usage) == 8
    assert all(row[1] == job_id for row in app.state.pool.usage)
    status_response = await client.get("/status")
    assert status_response.status_code == 200
    assert status_response.json()["llm"]["spend_usd"] == pytest.approx(0.04)
    assert "fixture-private-key" not in status_response.text + startup + caplog.text


@pytest.mark.parametrize(
    "wired_app,reason",
    [
        ({"key": None}, "model not configured"),
        ({"primary": "", "legacy": ""}, "set MODEL_PRIMARY"),
    ],
    indirect=["wired_app"],
)
async def test_unconfigured_model_is_reviewable(wired_app, model_case, reason, caplog):
    app, client = wired_app
    report, route = model_case
    services = app.state.services
    assert services.model_gateway is None and services.review.model is None
    model_status = (await client.get("/status")).json()["providers"]["model"]
    assert model_status == {"state": "UNCONFIGURED", "reason": reason}
    support = await services.backend.verify.verify_citation(
        report.paper.citations[0], report.sources[0]
    )
    assert support.label == "NEEDS_REVIEW" and support.needs_review_reason == reason
    assert not route.called
    startup = "\n".join(record.getMessage() for record in caplog.get_records("setup"))
    assert "model not configured:" in startup
    assert "fixture-private-key" not in startup + caplog.text


async def test_wired_model_budget_exhaustion_returns_needs_review(wired_app, model_case):
    app, client = wired_app
    report, route = model_case
    await Jobs(app.state.pool).record_spend(None, app.state.settings.llm_daily_budget)
    issues = []
    token = provider_issues.set(issues)
    try:
        result = await app.state.services.backend.verify.verify_citation(
            report.paper.citations[0], report.sources[0]
        )
    finally:
        provider_issues.reset(token)
    assert result.label == "NEEDS_REVIEW" and result.needs_review_reason
    assert issues == ["model: daily budget exhausted"]
    assert not route.called and len(app.state.pool.usage) == 1
    assert (await client.get("/status")).json()["llm"]["spend_usd"] == 0.05


async def test_wired_model_failures_open_status_breaker(wired_app, model_case):
    app, client = wired_app
    _, route = model_case
    route.respond(503)
    gateway = app.state.services.model_gateway
    gateway.attempts = 1
    for _ in range(3):
        with pytest.raises(ModelFailure):
            await app.state.services.review.model.complete(
                task="fixture", system="fixture", data="fixture", schema={}
            )
    assert (await client.get("/status")).json()["providers"]["model"]["state"] == "OPEN"
    with pytest.raises(ModelFailure):
        await app.state.services.review.model.complete(
            task="fixture", system="fixture", data="fixture", schema={}
        )
    assert route.call_count == 3


async def test_multiple_origins_and_first_origin_share_link(wired_app):
    app, client = wired_app
    assert app.state.frontend_origins == ["https://first.example", "https://second.example"]
    for origin, allowed in (
        ("https://first.example", True),
        ("https://second.example", True),
        ("http://localhost:3000", True),
        ("https://other.example", False),
    ):
        response = await client.options(
            "/jobs", headers={"Origin": origin, "Access-Control-Request-Method": "POST"}
        )
        assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)
    job_id = await Jobs(app.state.pool).create("share-test", {"sha256": "b" * 64})
    response = await client.post(f"/jobs/{job_id}/share")
    assert response.status_code == 200
    assert response.json()["url"] == f"https://first.example/shares/{response.json()['token']}"
