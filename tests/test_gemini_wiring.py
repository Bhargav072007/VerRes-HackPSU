"""Run all production model tasks against a fixture-backed Gemini transport."""

import json
from unittest.mock import AsyncMock

import httpx

from api.app import main
from api.app.settings import Settings
from tests import test_model_wiring

model_case = test_model_wiring.model_case


async def test_gemini_primary_runs_support_graph_and_full_review_panel(
    monkeypatch, job_pool, model_case, respx_mock
):
    monkeypatch.delenv("STUBS")
    monkeypatch.setenv("MODEL_PRIMARY", "gemini-3.6-flash")
    monkeypatch.setenv("MODEL_ADJUDICATOR", "")
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    report, _, responses = model_case
    seen = []

    def respond(request):
        payload = json.loads(request.content)
        task = payload["response_format"]["json_schema"]["name"]
        seen.append(task)
        assert request.headers["authorization"] == "Bearer fixture-gemini-key"
        assert payload["model"] == "gemini-3.6-flash" and "temperature" not in payload
        return httpx.Response(
            200,
            json={
                "model": "gemini-3.6-flash",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(responses[task])}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100},
            },
        )

    route = respx_mock.post(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    ).mock(side_effect=respond)
    app = main.create_app(
        Settings(
            _env_file=None,
            env="test",
            openai_api_key=None,
            gemini_api_key="fixture-gemini-key",
            llm_daily_budget=1,
        )
    )
    async with app.router.lifespan_context(app):
        backend = app.state.services.backend
        support = await backend.verify.verify_citation(report.paper.citations[0], report.sources[0])
        graph = await backend.graph.build_claim_map(report.paper)
        review = await app.state.services.review.run_review_panel(report.paper, report.support)
        assert support.label == "SUPPORTED" and support.model_id == "gemini-3.6-flash"
        assert graph.status == "COMPLETE" and len(review.comments) == len(review.top_fixes) == 3
        assert route.call_count == 8 and set(seen) == {
            "classify",
            "split",
            "judge",
            "claim_map",
            "r1_methods",
            "r2_evidence",
            "r3_claims",
            "chair",
        }
        assert len(job_pool.usage) == 8 and all(row[3] for row in job_pool.usage)
    assert all(client.is_closed for client in app.state.services.model_gateway.clients.values())
