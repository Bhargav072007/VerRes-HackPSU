import json
from copy import deepcopy
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
    return report, route, responses


@pytest.fixture
def disputed_case(model_case):
    report, _, responses = model_case
    report.paper.citations[0].claim_text = "Treatment did not improve outcomes in adults."
    responses["split"]["claims"][0]["text"] = report.paper.citations[0].claim_text
    responses["judge"].update(
        label="CONTRADICTED",
        reason="The source states improvement, contradicting the claim.",
        model_id="untrusted-model-id",
    )
    responses["adjudicate"] = deepcopy(responses["judge"])
    return model_case


@pytest.fixture
async def wired_app(monkeypatch, job_pool, request, tmp_path):
    config = getattr(request, "param", {})
    monkeypatch.delenv("STUBS")
    monkeypatch.setenv("MODEL_PRIMARY", config.get("primary", "fixture-primary"))
    monkeypatch.setenv("REVIEW_MODEL", config.get("legacy", "fixture-legacy"))
    monkeypatch.setenv("MODEL_ADJUDICATOR", config.get("adjudicator", ""))
    monkeypatch.delenv("ADJUDICATOR_ALLOW_SAME_VENDOR", raising=False)
    monkeypatch.setenv(
        "MODEL_PRICES",
        json.dumps(
            {name: [1, 2] for name in ("fixture-primary", "fixture-legacy", "fixture-adjudicator")}
        ),
    )
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
    report, route, _ = model_case
    services = app.state.services
    model = services.review.model
    assert model.model_id == expected_model
    assert model.gateway is services.model_gateway
    assert services.backend.verify.primary is services.backend.graph.model is model
    assert services.backend.verify.adjudicator is None
    startup = "\n".join(record.getMessage() for record in caplog.get_records("setup"))
    assert (
        startup.count(f"model configured: openai/{model.model_id}, adjudicator: openai/none") == 1
    )
    assert startup.count("Historical unknown-cost LLM rows remain flagged") == 1
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
    report, route, _ = model_case
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
    report, route, _ = model_case
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


@pytest.mark.parametrize("wired_app", [{"primary": "unlisted-model"}], indirect=True)
async def test_estimated_spend_enforces_budget_with_legacy_unknowns(wired_app, model_case):
    app, client = wired_app
    report, route, _ = model_case
    jobs = Jobs(app.state.pool)
    await jobs.record_spend(None, None)
    app.state.pool.legacy_unknown.add(app.state.pool.usage[-1][0])
    await jobs.record_spend(None, 0.032)
    result = await app.state.services.backend.verify.verify_citation(
        report.paper.citations[0], report.sources[0]
    )
    assert result.label == "NEEDS_REVIEW" and result.needs_review_reason
    assert route.call_count == 1  # 0.032 known + 0.018 estimated reaches the budget.
    response = await client.get("/status")
    assert response.status_code == 200
    llm = response.json()["llm"]
    assert llm["accounting"] == "estimated" and llm["estimated_calls"] == 1
    assert llm["known_spend_usd"] == 0.032 and llm["estimated_spend_usd"] == 0.018
    assert llm["spend_usd"] == 0.05 and llm["legacy_unknown_calls"] == llm["unknown_calls"] == 1
    assert not llm["accounting_incomplete"]


async def test_wired_model_failures_open_status_breaker(wired_app, model_case):
    app, client = wired_app
    _, route, _ = model_case
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


@pytest.mark.parametrize("wired_app", [{"adjudicator": " fixture-adjudicator "}], indirect=True)
@pytest.mark.parametrize("outcome", ["agree", "disagree", "bad_quote", "supported"])
async def test_openai_adjudication_and_honest_provenance(wired_app, disputed_case, outcome, caplog):
    app, client = wired_app
    report, route, responses = disputed_case
    if outcome == "supported":
        responses["judge"]["label"] = "SUPPORTED"
    elif outcome == "disagree":
        responses["adjudicate"]["label"] = "SUPPORTED"
    elif outcome == "bad_quote":
        responses["adjudicate"]["evidence"][0]["quote"] = "An invented quote about other outcomes."
    services = app.state.services
    assert services.adjudicator_model is services.backend.verify.adjudicator
    assert (
        services.adjudicator_model.gateway
        is services.primary_model.gateway
        is services.model_gateway
    )
    result = await services.backend.verify.verify_citation(
        report.paper.citations[0], report.sources[0]
    )
    calls = [json.loads(call.request.content) for call in route.calls]
    tasks = [call["response_format"]["json_schema"]["name"] for call in calls]
    assert tasks == ["classify", "split", "judge"] + (
        [] if outcome == "supported" else ["adjudicate"]
    )
    assert all(call["model"] == "fixture-primary" for call in calls[:3])
    assert result.prompt_version == "v2" and "untrusted-model-id" not in result.model_dump_json()
    assert "fixture-primary (vendor=openai, family=openai)" in result.reason
    if outcome == "supported":
        assert result.label == "SUPPORTED" and not result.adjudicated
        assert result.model_id == "fixture-primary" and "fixture-adjudicator" not in result.reason
    else:
        assert calls[-1]["model"] == "fixture-adjudicator"
        assert result.model_id == "fixture-primary, fixture-adjudicator"
        assert "fixture-adjudicator (vendor=openai, family=openai)" in result.reason
        assert "second-model check (same vendor)" in result.reason
        assert "independent" not in result.reason
        assert result.label == ("CONTRADICTED" if outcome == "agree" else "NEEDS_REVIEW")
        assert result.adjudicated == (outcome == "agree")
    assert all(e.quote in report.sources[0].passages[0].text for e in result.evidence)
    status = (await client.get("/status")).json()
    assert status["models"] == {
        role: {"model_id": model_id, "vendor": "openai", "family": "openai", "state": "CLOSED"}
        for role, model_id in (
            ("primary", "fixture-primary"),
            ("adjudicator", "fixture-adjudicator"),
        )
    }
    assert len(app.state.pool.usage) == len(calls)
    assert status["llm"]["spend_usd"] == pytest.approx(len(calls) * 0.005)
    startup = "\n".join(record.getMessage() for record in caplog.get_records("setup"))
    assert (
        "model configured: openai/fixture-primary, adjudicator: openai/fixture-adjudicator"
        in startup
    )
    assert "fixture-private-key" not in startup + caplog.text + json.dumps(status)


@pytest.mark.parametrize("wired_app", [{}, {"adjudicator": "fixture-primary"}], indirect=True)
async def test_unset_or_identical_adjudicator_preserves_review_fallback(wired_app, disputed_case):
    app, client = wired_app
    report, route, _ = disputed_case
    result = await app.state.services.backend.verify.verify_citation(
        report.paper.citations[0], report.sources[0]
    )
    assert result.label == "NEEDS_REVIEW" and not result.adjudicated
    assert result.model_id == "fixture-primary" and route.call_count == 3
    assert "second-model check" not in result.reason
    if app.state.services.adjudicator_model is None:
        assert (await client.get("/status")).json()["models"]["adjudicator"][
            "state"
        ] == "UNCONFIGURED"


@pytest.mark.parametrize("wired_app", [{"adjudicator": "fixture-adjudicator"}], indirect=True)
async def test_adjudicator_uses_primary_daily_budget(wired_app, disputed_case):
    app, client = wired_app
    report, route, _ = disputed_case
    await Jobs(app.state.pool).record_spend(None, 0.035)
    issues = []
    token = provider_issues.set(issues)
    try:
        result = await app.state.services.backend.verify.verify_citation(
            report.paper.citations[0], report.sources[0]
        )
    finally:
        provider_issues.reset(token)
    assert result.label == "NEEDS_REVIEW" and not result.adjudicated
    assert route.call_count == 3 and issues == ["model: daily budget exhausted"]
    assert (await client.get("/status")).json()["llm"]["spend_usd"] == 0.05


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
