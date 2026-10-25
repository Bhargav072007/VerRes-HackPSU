from datetime import timedelta
from uuid import UUID

import httpx
import pytest

from api.app import main
from api.app.db import Jobs
from api.app.settings import Settings
from tests import test_jobs

job_app = test_jobs.job_app
job_client = test_jobs.job_client
intake = test_jobs.intake


def test_rate_limit_settings(monkeypatch):
    for key in ("JOBS_PER_HOUR_PER_IP", "RATE_LIMIT_ALLOWLIST", "FORWARDED_ALLOW_IPS"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.jobs_per_hour_per_ip == 100
    assert settings.rate_limit_allowlist == settings.forwarded_allow_ips == ""
    monkeypatch.setenv("JOBS_PER_HOUR_PER_IP", "2")
    monkeypatch.setenv("RATE_LIMIT_ALLOWLIST", "192.0.2.1, 2001:db8::1")
    configured = Settings(_env_file=None)
    assert configured.jobs_per_hour_per_ip == 2
    assert configured.rate_limit_allowlist == "192.0.2.1, 2001:db8::1"


@pytest.mark.parametrize("limit", [1, 2, 7])
async def test_configured_limit_and_retry(job_client, job_app, job_pool, intake, limit):
    job_app.state.settings.jobs_per_hour_per_ip = limit
    for _ in range(limit):
        assert (await job_client.post("/jobs", json=intake["doi"])).status_code == 202
    response = await job_client.post("/jobs", json=intake["doi"])
    assert response.status_code == 429
    failure = response.json()
    assert failure["code"] == "rate_limited"
    assert f"Hourly limit of {limit}" in failure["message"]
    assert 3590 <= failure["retry_after_seconds"] <= 3600
    assert response.headers["Retry-After"] == str(failure["retry_after_seconds"])
    assert len(job_pool.rows) == limit
    assert (await job_client.get("/status")).json()["jobs_per_hour_per_ip"] == limit


async def test_lowered_limit_retry_waits_for_enough_jobs_to_expire(
    job_client, job_app, job_pool, intake
):
    for age in (50, 40, 10):
        response = await job_client.post("/jobs", json=intake["doi"])
        job_pool.rows[UUID(response.json()["job_id"])]["created_at"] -= timedelta(minutes=age)
    job_app.state.settings.jobs_per_hour_per_ip = 2
    response = await job_client.post("/jobs", json=intake["doi"])
    assert response.status_code == 429
    assert 1190 <= response.json()["retry_after_seconds"] <= 1200


@pytest.mark.parametrize("ip", ["192.0.2.1", "2001:db8::1"])
async def test_allowlisted_ip_exempt(job_pool, intake, ip):
    store = Jobs(
        job_pool,
        Settings(
            _env_file=None,
            jobs_per_hour_per_ip=1,
            rate_limit_allowlist=" 192.0.2.1, 2001:db8::1 , ",
        ),
    )
    for _ in range(3):
        assert isinstance(await store.create(ip, intake["doi"]), UUID)
    for index in range(3):
        assert isinstance(await store.create(ip, {"index": index}, running=True), UUID)
    failure = await store.create(ip, {}, running=True)
    assert failure.code == "rate_limited" and failure.retry_after_seconds == 60


async def test_cache_hit_exempt_and_not_counted(job_client, job_app, intake, events):
    job_app.state.settings.jobs_per_hour_per_ip = 1
    response = await job_client.post("/jobs", json=intake["doi"])
    original = UUID(response.json()["job_id"])
    report = {**events[-2]["payload"], "job_id": str(original)}
    await job_app.state.event_bus.emit(original, "done", report)
    for _ in range(3):
        assert (await job_client.post("/jobs", json=intake["doi"])).status_code == 202
    assert (await job_client.post("/jobs", json=intake["arxiv"])).status_code == 429
    job_app.state.settings.jobs_per_hour_per_ip = 2
    assert (await job_client.post("/jobs", json=intake["arxiv"])).status_code == 202
    assert (await job_client.post("/jobs?fresh=1", json=intake["doi"])).status_code == 429


@pytest.mark.parametrize("trusted", [False, True])
async def test_forwarded_client_buckets_and_spoofing(job_app, job_pool, intake, trusted):
    job_app.state.settings.jobs_per_hour_per_ip = 1
    job_app.state.settings.forwarded_allow_ips = "172.30.0.2"
    app = main.create_app(job_app.state.settings)
    peer = "172.30.0.2" if trusted else "192.0.2.90"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(peer, 1234)),
            base_url="http://test",
        ) as client,
    ):
        for index, ip in enumerate(("203.0.113.1", "203.0.113.2")):
            response = await client.post(
                "/jobs", json=intake["doi"], headers={"X-Forwarded-For": f"198.51.100.9, {ip}"}
            )
            assert response.status_code == (202 if trusted or index == 0 else 429)
        response = await client.post(
            "/jobs", json=intake["doi"], headers={"X-Forwarded-For": "203.0.113.1"}
        )
        assert response.status_code == 429
    assert {row["client_ip"] for row in job_pool.rows.values()} == (
        {"203.0.113.1", "203.0.113.2"} if trusted else {peer}
    )
