import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
pytest_plugins = ["tests.job_fixtures"]


@pytest.fixture(autouse=True)
def fixture_services(monkeypatch):
    monkeypatch.setenv("STUBS", "1")


@pytest.fixture(autouse=True)
def block_live_http(respx_mock):
    """respx rejects every HTTP call without an explicit fixture-backed route."""
    return respx_mock


@pytest.fixture
def events():
    return json.loads((FIXTURES / "events" / "job.json").read_text())


@pytest.fixture
def health_responses():
    return json.loads((FIXTURES / "providers" / "health.json").read_text())


@pytest.fixture
def migration_directory():
    return FIXTURES / "providers" / "migrations"
