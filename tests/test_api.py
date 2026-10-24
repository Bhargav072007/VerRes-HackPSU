from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient

from api.app import main
from api.app.providers.http import get_client
from api.app.settings import Settings


@pytest.fixture
def application(monkeypatch):
    pool = AsyncMock()
    pool.fetchval.return_value = 1
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    return main.create_app(Settings(_env_file=None, env="test")), pool


def test_settings_from_env_and_secret_redaction(monkeypatch):
    monkeypatch.setenv("GROBID_URL", "http://grobid.example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:private@db/verres")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-private-key")
    settings = Settings(_env_file=None)
    assert settings.grobid_url == "http://grobid.example"
    assert settings.database_url.get_secret_value().endswith("@db/verres")
    assert "fixture-private-key" not in repr(settings)
    assert "user:private" not in repr(settings)
    monkeypatch.setenv("GROBID_URL", "")
    assert Settings(_env_file=None).grobid_url == "http://127.0.0.1:8070"


def test_health_and_lifespan(application, respx_mock, health_responses):
    app, pool = application
    fixture = health_responses["healthy"]
    respx_mock.get(app.state.settings.grobid_url + "/api/isalive").respond(
        fixture["status"], text=fixture["body"]
    )
    with TestClient(app) as client:
        result = client.get("/health")
        assert result.status_code == 200
        assert result.json() == {"status": "ok", "db": "ok", "grobid": "ok", "reason": None}
        main.run_migrations.assert_awaited_once_with(pool)
    pool.close.assert_awaited_once()
    assert app.state.grobid_client.is_closed


@pytest.mark.parametrize("case", ["not_ready", "unavailable", "unexpected", "timeout"])
def test_health_grobid_failure(application, respx_mock, health_responses, case):
    app, _ = application
    route = respx_mock.get(app.state.settings.grobid_url + "/api/isalive")
    if case == "timeout":
        route.mock(side_effect=httpx.ReadTimeout("fixture timeout"))
    else:
        fixture = health_responses[case]
        route.respond(fixture["status"], text=fixture["body"])
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["grobid"] == "CHECK_INCOMPLETE"
        assert response.json()["db"] == "ok"


@pytest.mark.parametrize("startup", [True, False])
def test_health_db_failure(application, monkeypatch, respx_mock, startup):
    app, pool = application
    if startup:
        monkeypatch.setattr(main, "create_pool", AsyncMock(side_effect=OSError("private details")))
    else:
        pool.fetchval.side_effect = asyncpg.PostgresConnectionError("private details")
    respx_mock.get(app.state.settings.grobid_url + "/api/isalive").respond(200, text="true")
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["db"] == "CHECK_INCOMPLETE"
        assert "private details" not in response.text


def test_migration_failure_closes_resources(application, monkeypatch):
    app, pool = application
    monkeypatch.setattr(main, "run_migrations", AsyncMock(side_effect=RuntimeError("DDL failed")))
    with pytest.raises(RuntimeError, match="DDL failed"), TestClient(app):
        pass
    pool.close.assert_awaited_once()
    assert app.state.grobid_client.is_closed


def test_openapi_includes_all_contracts(application):
    app, _ = application
    schema = app.openapi()
    assert app.openapi() is schema
    definitions = schema["components"]["schemas"]
    for name in (
        "Report",
        "Paper",
        "Judgment",
        "SupportResult",
        "ReviewSummary",
        "StageEvent",
        "PaperEvent",
        "ExistenceEvent",
        "RetractionEvent",
        "SourceEvent",
        "SupportEvent",
        "ClaimMapEvent",
        "HiddenTextEvent",
        "ReviewEvent",
        "ReviewSummaryEvent",
        "DoneEvent",
        "ErrorEvent",
        "SSEEvent",
    ):
        assert name in definitions
    assert "/health" in schema["paths"]
    assert len(definitions["SSEEvent"]["discriminator"]["mapping"]) == 12


async def test_http_client_shared_per_provider_and_recreated_after_close():
    first = get_client("fixture")
    other = get_client("other-fixture")
    assert get_client("fixture") is first
    assert first is not other
    assert first.timeout.connect == 5
    assert first.timeout.read == 20
    await first.aclose()
    replacement = get_client("fixture")
    assert replacement is not first
    await replacement.aclose()
    await other.aclose()
