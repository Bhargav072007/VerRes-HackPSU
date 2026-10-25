import asyncio
import json
import secrets
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import asyncpg
import httpx
import pytest

from api.app import main, version
from api.app.routes import share_store
from api.app.routes.share_store import Shares
from api.app.settings import Settings
from contracts.schema import Report
from tests.conftest import FIXTURES


@pytest.fixture
def receipt_fixture():
    return json.loads((FIXTURES / "shares" / "provenance.json").read_text())


@pytest.fixture
async def share_client(monkeypatch, job_pool):
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=job_pool))
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    app = main.create_app(Settings(_env_file=None, env="test"))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app


@pytest.fixture
async def receipt(share_client, job_pool, events, receipt_fixture):
    _, app = share_client
    fixture = receipt_fixture
    store = app.state.event_bus.jobs
    job_id = await store.create(
        fixture["private"]["ip"], {**fixture["job_input"], "pdf_bytes": fixture["private"]["pdf"]}
    )
    report = deepcopy(events[-2]["payload"])
    report["job_id"] = str(job_id)
    report["paper"]["sentences"].append({"id": "private", "text": fixture["private"]["sentence"]})
    report["sources"][0]["passages"].append(
        {"passage_id": "private", "text": fixture["private"]["passage"]}
    )
    report["sources"][0].update(fixture["source"])
    report["existence"][0].update(status="DOI_MISMATCH", **fixture["source"])
    report["retractions"][0].update(status="RETRACTED", **fixture["source"])
    report["support"][0].update(label="CONTRADICTED", **fixture["verdict"])
    for stage in fixture["stage_events"]:
        await store.append(
            job_id, "stage", {key: value for key, value in stage.items() if key != "at"}
        )
        job_pool.events[-1]["created_at"] = datetime.fromisoformat(stage["at"])
    await store.append(
        job_id, "error", {"code": "CHECK_INCOMPLETE", "reason": fixture["private"]["trace"]}
    )
    await store.append(job_id, "done", report)
    job_pool.events[-1]["created_at"] = datetime.fromisoformat(fixture["finished_at"])
    return job_id


async def test_share_lifecycle_and_private_projection(
    share_client, receipt, job_pool, receipt_fixture
):
    client, _ = share_client
    response = await client.post(f"/jobs/{receipt}/share")
    assert response.status_code == 200
    created = response.json()
    token = created["token"]
    assert len(token) == 22 and token != str(receipt)
    assert set(created) == {"token", "url", "expires_at"}
    assert created["url"] == f"http://localhost:3000/shares/{token}"
    expires = datetime.fromisoformat(created["expires_at"])
    assert (
        timedelta(days=30) - timedelta(seconds=2) < expires - datetime.now(UTC) < timedelta(days=30)
    )
    response = await client.get(created["url"])
    assert response.status_code == 200 and response.json()["shared"] is True
    public = response.json()
    assert not {"job", "events", "errors", "stages"} & public.keys()
    assert "sentences" not in public["paper"] and "passages" not in public["sources"][0]
    assert all(secret not in response.text for secret in receipt_fixture["private"].values())
    assert public["paper"]["citations"] and public["claim_map"] and public["hidden_text"]
    assert public["review"]["comments"] and public["support"][0]["evidence"][0]["quote"]
    assert job_pool.shares[token]["view_count"] == 1
    for format in ("json", "md"):
        exported = await client.get(f"/shares/{token}/export?format={format}")
        assert exported.status_code == 200
        assert all(secret not in exported.text for secret in receipt_fixture["private"].values())
        if format == "json":
            assert exported.json() == public
    assert job_pool.shares[token]["view_count"] == 3
    assert (await client.delete(f"/shares/{token}")).status_code == 204
    for suffix in ("", "/export?format=md", "/export?format=json"):
        gone = await client.get(f"/shares/{token}{suffix}")
        assert gone.status_code == 410 and "revoked" in gone.json()["message"]
    assert job_pool.shares[token]["view_count"] == 3


@pytest.mark.parametrize("days", [1, 90])
async def test_share_expiration(share_client, receipt, job_pool, days):
    client, _ = share_client
    result = (await client.post(f"/jobs/{receipt}/share?days={days}")).json()
    row = job_pool.shares[result["token"]]
    assert row["expires_at"] - row["created_at"] == timedelta(days=days)
    row["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    for suffix in ("", "/export?format=json", "/export?format=md"):
        result = await client.get(f"/shares/{row['token']}{suffix}")
        assert result.status_code == 410 and "expired" in result.json()["message"]
    assert (await client.delete(f"/shares/{row['token']}")).status_code == 410
    assert row["view_count"] == 0


async def test_share_limit_is_atomic_per_ip_and_survives_revocation(
    share_client, receipt, job_pool
):
    client, _ = share_client
    results = await asyncio.gather(*(client.post(f"/jobs/{receipt}/share") for _ in range(21)))
    assert sum(result.status_code == 200 for result in results) == 20
    assert sum(result.status_code == 429 for result in results) == 1
    token = next(iter(job_pool.shares))
    await client.delete(f"/shares/{token}")
    assert (await client.post(f"/jobs/{receipt}/share")).status_code == 429
    assert not isinstance(
        await Shares(job_pool).create(receipt, "different-ip", 30), share_store.JobFailure
    )
    for row in job_pool.share_creations.values():
        row["created_at"] -= timedelta(hours=2)
    assert (await client.post(f"/jobs/{receipt}/share")).status_code == 200


async def test_constant_time_comparison(share_client, receipt, monkeypatch, job_pool):
    client, _ = share_client
    token = (await client.post(f"/jobs/{receipt}/share")).json()["token"]
    compare = Mock(wraps=secrets.compare_digest)
    monkeypatch.setattr(share_store.secrets, "compare_digest", compare)
    assert (await client.get(f"/shares/{token}")).status_code == 200
    compare.assert_called_once_with(token, token)
    missing = "x" * 22
    assert (await client.get(f"/shares/{missing}")).status_code == 404
    compare.assert_called_with(missing, "0" * 22)
    monkeypatch.setattr(job_pool, "fetchrow", AsyncMock(return_value={"token": missing}))
    assert (await client.get(f"/shares/{token}")).status_code == 404


async def test_provenance_and_export_receipts(share_client, receipt, receipt_fixture):
    client, _ = share_client
    report = (await client.get(f"/jobs/{receipt}")).json()
    assert report["pipeline_version"] == version.PIPELINE_VERSION
    assert report["git_sha"] == version.GIT_SHA
    assert report["pdf_sha256"] == receipt_fixture["job_input"]["sha256"]
    assert report["started_at"] == "2024-06-01T12:00:00Z"
    assert report["finished_at"] == receipt_fixture["finished_at"]
    assert report["stage_durations"] == {"parse": 3.5, "verify": 3.0}
    row = report["support"][0]
    assert all(row[key] == value for key, value in receipt_fixture["source"].items())
    assert all(row[key] == value for key, value in receipt_fixture["verdict"].items())
    assert row["evidence_level"] == row["evidence"][0]["evidence_level"] == "FULL_TEXT"
    assert row["evidence"][0]["source_url"] == receipt_fixture["source"]["source_url"]
    assert report["existence"][0]["model_id"] is None
    exported = await client.get(f"/jobs/{receipt}/export?format=json")
    assert exported.json() == report
    markdown = await client.get(f"/jobs/{receipt}/export?format=md")
    assert markdown.headers["content-type"].startswith("text/markdown")
    for text in (
        "Summary counts",
        "ref-1: DOI_MISMATCH",
        "ref-1: RETRACTED",
        "cite-1: CONTRADICTED",
        row["evidence"][0]["quote"],
        row["source_url"],
        row["retrieved_at"],
    ):
        assert text in markdown.text


async def test_old_reports_and_running_jobs_without_provenance(share_client, events):
    client, app = share_client
    old = Report.model_validate(events[-2]["payload"])
    assert old.pipeline_version is None and old.existence[0].retrieved_at is None
    store = app.state.event_bus.jobs
    job_id = await store.create("old-job", {})
    empty = (await client.get(f"/jobs/{job_id}")).json()
    assert all(
        empty[field] is None
        for field in ("pdf_sha256", "started_at", "finished_at", "stage_durations")
    )
    await store.append(job_id, "done", {**events[-2]["payload"], "job_id": str(job_id)})
    report = (await client.get(f"/jobs/{job_id}")).json()
    assert report["existence"][0]["source_url"] == "https://example.org/trial"
    assert report["sources"][0]["retrieved_at"] is None
    assert report["support"][0]["model_id"] is None
    assert report["support"][0]["prompt_version"] is None
    assert report["support"][0]["quote_offsets"] is None
    assert report["finished_at"] and report["started_at"] is None
    token = (await client.post(f"/jobs/{job_id}/share")).json()["token"]
    markdown = await client.get(f"/shares/{token}/export?format=md")
    assert markdown.status_code == 200 and "Unavailable" in markdown.text


async def test_invalid_missing_and_storage_errors(share_client, receipt, monkeypatch, job_pool):
    client, app = share_client
    for days in ("0", "91", "abc"):
        assert (await client.post(f"/jobs/{receipt}/share?days={days}")).status_code == 400
    assert (await client.post(f"/jobs/{uuid4()}/share")).status_code == 404
    for token in ("bad", "x" * 22, str(receipt)):
        assert (await client.get(f"/shares/{token}")).status_code == 404
        assert (await client.delete(f"/shares/{token}")).status_code == 404
    assert (await client.get(f"/jobs/{receipt}/export?format=pdf")).status_code == 400
    assert (await client.get(f"/jobs/{uuid4()}/export")).status_code == 404
    monkeypatch.setattr(
        job_pool, "fetchrow", AsyncMock(side_effect=asyncpg.PostgresError("private trace"))
    )
    failed = await client.get(f"/shares/{'x' * 22}")
    assert failed.status_code == 503 and "private" not in failed.text
    app.state.event_bus = None
    for method, path in (
        ("post", f"/jobs/{receipt}/share"),
        ("get", "/shares/bad"),
        ("delete", "/shares/bad"),
        ("get", "/shares/bad/export"),
    ):
        assert (await client.request(method, path)).status_code == 503


def test_share_openapi_and_generated_schema():
    app = main.create_app(Settings(_env_file=None))
    schema = app.openapi()
    assert json.loads((FIXTURES.parent / "web" / "openapi.json").read_text()) == schema
    shared = schema["components"]["schemas"]["SharedSnapshot"]["properties"]
    assert "shared" in shared and not {"job", "events", "errors"} & shared.keys()
    assert "sentences" not in schema["components"]["schemas"]["SharedPaper"]["properties"]
    assert "passages" not in schema["components"]["schemas"]["SharedSource"]["properties"]
    for path in ("/jobs/{job_id}/export", "/shares/{token}/export"):
        content = schema["paths"][path]["get"]["responses"]["200"]["content"]
        assert set(content) == {"application/json", "text/markdown"}
    assert "410" in schema["paths"]["/shares/{token}"]["get"]["responses"]
