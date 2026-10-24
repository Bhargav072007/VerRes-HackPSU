import inspect
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from contracts import interfaces
from contracts.events import SSEEvent
from contracts.schema import Judgment, Paper, Report, SupportResult


def test_event_union_round_trip(events):
    adapter = TypeAdapter(SSEEvent)
    assert {event["type"] for event in events} == {
        "stage",
        "paper",
        "existence",
        "retraction",
        "source",
        "support",
        "claim_map",
        "hidden_text",
        "review",
        "review_summary",
        "done",
        "error",
    }
    for event in events:
        parsed = adapter.validate_python(event)
        assert adapter.validate_json(adapter.dump_json(parsed)) == parsed
    Report.model_validate(events[-2]["payload"])


@pytest.mark.parametrize("field,value", [("type", "invented"), ("seq", 0), ("job_id", "bad")])
def test_invalid_event_envelope_rejected(events, field, value):
    event = deepcopy(events[0])
    event[field] = value
    with pytest.raises(ValidationError):
        TypeAdapter(SSEEvent).validate_python(event)


def test_event_payload_matches_type(events):
    event = deepcopy(events[0])
    event["payload"] = events[1]["payload"]
    with pytest.raises(ValidationError):
        TypeAdapter(SSEEvent).validate_python(event)


def test_verdict_requires_receipts(events):
    payload = deepcopy(events[5]["payload"])
    payload["evidence"] = []
    with pytest.raises(ValidationError, match="requires evidence"):
        SupportResult.model_validate(payload)
    payload.update(label="NEEDS_REVIEW", evidence_strength="INSUFFICIENT")
    with pytest.raises(ValidationError, match="requires needs_review_reason"):
        SupportResult.model_validate(payload)
    payload["needs_review_reason"] = "Full text unavailable"
    assert SupportResult.model_validate(payload).label == "NEEDS_REVIEW"


def test_unknown_fields_and_blank_quotes_rejected(events):
    payload = deepcopy(events[5]["payload"])
    payload["confidence"] = "forbidden"
    with pytest.raises(ValidationError, match="Extra inputs"):
        SupportResult.model_validate(payload)
    del payload["confidence"]
    payload["evidence"][0]["quote"] = " "
    with pytest.raises(ValidationError):
        SupportResult.model_validate(payload)


def test_insufficient_evidence_requires_review(events):
    payload = deepcopy(events[5]["payload"])
    payload["evidence_strength"] = "INSUFFICIENT"
    with pytest.raises(ValidationError, match="use NEEDS_REVIEW"):
        SupportResult.model_validate(payload)


def test_contracts_do_not_expose_numeric_confidence():
    schema = TypeAdapter(Report | SSEEvent).json_schema()
    for definition in schema["$defs"].values():
        assert not any("confidence" in key.lower() for key in definition.get("properties", {}))


def test_judgment_is_llm_schema(events):
    support = SupportResult.model_validate(events[5]["payload"])
    payload = support.model_dump(exclude={"citation_id", "needs_review_reason", "adjudicated"})
    assert Judgment.model_validate(payload).evidence[0].passage_id == "p1"


def test_interfaces_are_async_and_fixture_stub_is_injectable(events):
    methods = []
    for interface in (
        interfaces.Ingest,
        interfaces.Resolve,
        interfaces.Sources,
        interfaces.Verify,
        interfaces.Graph,
        interfaces.Review,
    ):
        methods.extend(value for name, value in vars(interface).items() if not name.startswith("_"))
    assert len(methods) == 8
    assert all(inspect.iscoroutinefunction(method) for method in methods)


@pytest.mark.asyncio
async def test_ingest_fixture_stub(events):
    from unittest.mock import AsyncMock

    ingest = AsyncMock(spec=interfaces.Ingest)
    ingest.parse_pdf.return_value = Paper.model_validate(events[1]["payload"])
    assert (await ingest.parse_pdf(b"fixture input")).id == "paper-1"
