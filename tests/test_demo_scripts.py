import asyncio
import hashlib
import json
import sys
from copy import deepcopy
from uuid import UUID

import httpx
import pytest

from api.app.routes import demo
from scripts import demo_client, load_test, record_fixture, warm_demo
from tests.conftest import FIXTURES

BASE = "https://demo.example"
JOB_ID = str(UUID(int=1))


def stream_fixture(events):
    return (
        "\n\n".join(
            f"id: {e['seq']}\nevent: {e['type']}\ndata: {json.dumps(e['payload'])}" for e in events
        )
        + "\n\n"
    )


async def test_client_waits_for_done_counts_and_stage_times(respx_mock, events):
    recorded = deepcopy(events[:-1])
    recorded.insert(
        1, {"seq": 2, "type": "stage", "payload": {"stage": "parse", "status": "COMPLETED"}}
    )
    for index, event in enumerate(recorded, 1):
        event["seq"] = index
    posted = respx_mock.post(BASE + "/jobs").respond(202, json={"job_id": JOB_ID})
    stream = respx_mock.get(f"{BASE}/jobs/{JOB_ID}/events").respond(
        200, text=": heartbeat\n\n" + stream_fixture(recorded)
    )
    result = await demo_client.run_job(BASE, FIXTURES / "pdfs/paper1_attention.pdf", fresh=True)
    assert result["failure"] is None and result["job_id"] == JOB_ID
    assert result["report_url"] == f"{BASE}/jobs/{JOB_ID}"
    assert result["stages"]["parse"] >= 0 and result["duration_seconds"] > 0
    assert result["counts"]["support"] == {"SUPPORTED": 1}
    assert posted.calls[0].request.url.params["fresh"] == "1"
    assert stream.calls[0].request.headers["Last-Event-ID"] == "0"


async def test_client_reconnects_after_incomplete_journal(respx_mock, events):
    respx_mock.post(BASE + "/jobs").respond(202, json={"job_id": JOB_ID})
    route = respx_mock.get(f"{BASE}/jobs/{JOB_ID}/events")
    route.side_effect = [
        httpx.Response(200, text=stream_fixture(events[:2])),
        httpx.Response(200, text=stream_fixture(events[1:-1])),
    ]
    result = await demo_client.run_job(BASE, FIXTURES / "pdfs/1_pages.pdf")
    assert result["failure"] is None and route.call_count == 2
    assert route.calls[1].request.headers["Last-Event-ID"] == "2"


@pytest.mark.parametrize(
    "failure", ["post", "sse", "empty", "malformed", "timeout", "incomplete", "file"]
)
async def test_client_failures_have_safe_reasons(respx_mock, events, tmp_path, failure):
    post = respx_mock.post(BASE + "/jobs").respond(
        429 if failure == "post" else 202, json={"job_id": JOB_ID}
    )
    route = respx_mock.get(f"{BASE}/jobs/{JOB_ID}/events")
    if failure == "timeout":
        route.mock(side_effect=httpx.ReadTimeout("private query credentials"))
    elif failure == "incomplete":
        done = deepcopy(events[-2])
        done["payload"].update(status="CHECK_INCOMPLETE", reason="Provider unavailable")
        route.respond(200, text=stream_fixture([done]))
    else:
        route.respond(
            503 if failure == "sse" else 200,
            text="id: 1\nevent: done\ndata: not-json\n\n" if failure == "malformed" else "",
        )
    path = tmp_path / "missing.pdf" if failure == "file" else FIXTURES / "pdfs/1_pages.pdf"
    result = await demo_client.run_job(BASE, path)
    assert result["failure"] and "private" not in result["failure"]
    assert result["duration_seconds"] >= 0
    if failure == "file":
        assert not post.called


async def test_multiline_sse_and_comments():
    response = httpx.Response(
        200, text=': ping\n\nid: 7\nevent: done\ndata: {\ndata: "status": "COMPLETE"}\n\n'
    )
    items = [event async for event in demo_client.sse_events(response)]
    assert items == [{"id": "7", "event": "done", "payload": {"status": "COMPLETE"}}]


async def test_warm_writes_all_three_and_reports_failure(respx_mock, events, tmp_path, capsys):
    post = respx_mock.post(BASE + "/jobs").respond(202, json={"job_id": JOB_ID})
    respx_mock.get(f"{BASE}/jobs/{JOB_ID}/events").respond(200, text=stream_fixture(events))
    output = tmp_path / "demo.json"
    assert await warm_demo.warm(BASE, output) == 0
    reports = json.loads(output.read_text())
    assert set(reports) == set(demo_client.PAPERS) and post.call_count == 3
    assert all(set(report) == {"job_id", "report_url"} for report in reports.values())
    assert len(capsys.readouterr().out.splitlines()) == 3
    post.respond(503)
    assert await warm_demo.warm(BASE, output) == 1


async def test_load_five_concurrent_and_failure_summary(monkeypatch, capsys):
    started = 0
    barrier = asyncio.Event()

    async def run(*args, **kwargs):
        nonlocal started
        started += 1
        if started == 5:
            barrier.set()
        await asyncio.wait_for(barrier.wait(), 1)
        assert kwargs["fresh"] is True
        return {"duration_seconds": started, "failure": None}

    monkeypatch.setattr(load_test, "run_job", run)
    assert await load_test.load(BASE) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["concurrency"] == report["completed"] == 5
    assert report["p50_seconds"] == report["p95_seconds"] == 5 and not report["failures"]

    async def failed(*args, **kwargs):
        return {"duration_seconds": 1, "failure": "HTTP 429"}

    monkeypatch.setattr(load_test, "run_job", failed)
    assert await load_test.load(BASE, 1) == 1
    assert load_test.percentile([], 0.95) is None
    assert load_test.percentile([1, 2, 3, 4, 5], 0.50) == 3
    assert load_test.percentile([1, 2, 3, 4, 5], 0.95) == 5


@pytest.mark.parametrize("paper,index", [(name, i) for i, name in enumerate(demo.DEMO_PAPERS, 1)])
async def test_record_completed_job_at_paper_specific_path(
    respx_mock, events, tmp_path, paper, index
):
    digest = hashlib.sha256((FIXTURES / f"pdfs/{paper}.pdf").read_bytes()).hexdigest()
    snapshot = {"job": {"input": {"sha256": digest}}, "events": events[:-1]}
    respx_mock.get(f"{BASE}/jobs/{JOB_ID}").respond(200, json=snapshot)
    directory = tmp_path / "demo"
    assert await record_fixture.record(JOB_ID, BASE, directory=directory) == 0
    recorded = [
        json.loads(line) for line in (directory / f"paper{index}.jsonl").read_text().splitlines()
    ]
    assert recorded[-1]["type"] == "done"
    assert all(event["input_sha256"] == digest for event in recorded)
    assert not isinstance(demo.validate_recording(recorded), str)


@pytest.mark.parametrize(
    "bad", ["demo", "unknown", "unfinished", "wrong_job", "http", "invalid", "stub"]
)
async def test_recorder_refuses_unusable_snapshots(respx_mock, events, tmp_path, bad):
    digest = hashlib.sha256((FIXTURES / "pdfs/paper1_attention.pdf").read_bytes()).hexdigest()
    snapshot = {"job": {"input": {"sha256": digest}}, "events": deepcopy(events[:-1])}
    if bad == "demo":
        snapshot["demo_fixture"] = True
    elif bad == "unknown":
        snapshot["job"]["input"] = {"sha256": "0" * 64}
    elif bad == "unfinished":
        snapshot["events"] = events[:3]
    elif bad == "wrong_job":
        for event in snapshot["events"]:
            event["job_id"] = str(UUID(int=2))
        snapshot["events"][-1]["payload"]["job_id"] = str(UUID(int=2))
    elif bad == "stub":
        snapshot["events"][-1]["payload"]["review"]["warning"] = "Review panel is a stub until A8."
    route = respx_mock.get(f"{BASE}/jobs/{JOB_ID}")
    if bad == "invalid":
        route.respond(200, text="not-json private")
    else:
        route.respond(503 if bad == "http" else 200, json=snapshot)
    assert await record_fixture.record(JOB_ID, BASE, directory=tmp_path) == 1
    assert not list(tmp_path.glob("*.jsonl"))


@pytest.mark.parametrize(
    "module,arguments",
    [
        (warm_demo, [BASE]),
        (load_test, [BASE, "-n", "5"]),
        (record_fixture, [JOB_ID, "--base-url", BASE]),
    ],
)
def test_cli_entry_points(module, arguments, monkeypatch, tmp_path, events, respx_mock):
    monkeypatch.setattr(sys, "argv", [module.__name__, *arguments])
    monkeypatch.chdir(tmp_path)

    # Exercise argument parsing and asyncio wiring without any live service.
    async def success(*args, **kwargs):
        return 0

    target = {warm_demo: "warm", load_test: "load", record_fixture: "record"}[module]
    monkeypatch.setattr(module, target, success)
    assert module.main() == 0


def test_load_cli_rejects_zero(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["load_test", "-n", "0"])
    with pytest.raises(SystemExit) as failure:
        load_test.main()
    assert failure.value.code == 2
