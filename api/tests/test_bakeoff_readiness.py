"""Offline readiness and report semantics; fixture predictions are not accuracy data."""

import json

import pytest

from api.app.eval.bakeoff import (
    HASH_KEYS,
    PAPERS,
    EvalPair,
    Prediction,
    canonical_source,
    dataset_readiness,
    fingerprint,
    human_labeled,
    main,
    normalized,
    pair_key,
    protocol_manifest,
    read_pairs,
    run_bakeoff,
    summarize,
)
from api.app.verify.model import ModelFailure
from api.tests.helpers import FixtureModel, judgment


@pytest.fixture
def reviewed_pairs(claim, source):
    """Deliberately synthetic unit-test records, never exported as real annotations."""
    return [
        EvalPair(
            id=f"fixture-{i}",
            paper_id=PAPERS[0 if i < 30 else (1 if i < 35 else 2)],
            citation_text=f"Unit-test-only distinct citation {i}: {claim.text}",
            claim=claim,
            source=source,
            human_label="SUPPORTED",
            labeled_by="unit-test fixture; not an authentic annotation",
            label_reason="Controlled fixture exercises runner validation only.",
            synthetic=i >= 30,
            citation_function="SPECIFIC_CLAIM",
            evidence_quote=source.text,
            provenance={
                **{name: "a" * 64 for name in HASH_KEYS},
                "source_id": source.work_id,
                "source_coverage": "FULL_TEXT",
            },
        )
        for i in range(40)
    ]


def models():
    return [
        FixtureModel({"judge": judgment().model_dump()}, model_id=name)
        for name in ("fixture-1", "fixture-2")
    ]


def test_readiness_requires_reviewed_metadata_and_evidence(reviewed_pairs):
    assert dataset_readiness(reviewed_pairs) == []
    pair = reviewed_pairs[0]
    pair.labeled_by = "  "
    pair.label_reason = " "
    pair.citation_function = None
    pair.synthetic = True
    pair.evidence_quote = "This exact quotation is invented"
    pair.provenance["source_receipt_sha256"] = "not a receipt"
    pair.provenance["source_id"] = "different-work"
    pair.provenance["source_coverage"] = "ABSTRACT_ONLY"
    issues = dataset_readiness(reviewed_pairs)
    for issue in (
        "annotator",
        "citation function",
        "synthetic flag",
        "evidence quote",
        "source_receipt_sha256",
        "source identity",
        "source coverage",
    ):
        assert any(issue in text for text in issues)
    assert not human_labeled(pair)


def test_readiness_missing_source_and_wrong_paper_names(reviewed_pairs):
    pair = reviewed_pairs[0]
    pair.paper_id = "paper1"
    pair.source = pair.source.model_copy(
        update={"evidence_level": "NONE", "text": "", "origin": None}
    )
    assert any("exact three" in issue for issue in dataset_readiness(reviewed_pairs))
    assert any("source evidence" in issue for issue in dataset_readiness(reviewed_pairs))


def test_normalization_and_duplicate_pairs_cannot_be_hidden_by_new_ids(reviewed_pairs, tmp_path):
    pair = reviewed_pairs[0]
    pair.source = pair.source.model_copy(update={"work_id": "https://doi.org/10.1234/Example"})
    duplicate = pair.model_copy(deep=True, update={"id": "different-id"})
    duplicate.citation_text = "  " + pair.citation_text.upper().replace(" ", "\n")
    duplicate.source.work_id = "doi:10.1234/example"
    assert pair_key(pair) == pair_key(duplicate)
    assert normalized("e\u0301  text") == "é text"
    assert canonical_source("https://arxiv.org/pdf/1706.03762v7.pdf") == "arxiv:1706.03762"
    assert canonical_source("10.1234/Example") == "doi:10.1234/example"
    reviewed_pairs[1] = duplicate
    assert any("duplicate normalized" in issue for issue in dataset_readiness(reviewed_pairs))
    path = tmp_path / "duplicates.jsonl"
    path.write_text(pair.model_dump_json() + "\n" + duplicate.model_dump_json())
    with pytest.raises(ValueError, match="duplicate normalized"):
        read_pairs(path)


@pytest.mark.parametrize("mutation", ["count", "duplicates", "unreviewed", "evidence"])
async def test_rejects_unready_before_any_model_call(reviewed_pairs, mutation):
    if mutation == "count":
        reviewed_pairs.pop()
    elif mutation == "duplicates":
        reviewed_pairs[1].citation_text = reviewed_pairs[0].citation_text
    elif mutation == "unreviewed":
        reviewed_pairs[0].human_label = None
    else:
        reviewed_pairs[0].source = reviewed_pairs[0].source.model_copy(update={"text": ""})
    adapters = models()
    with pytest.raises(ValueError, match="not benchmark-ready"):
        await run_bakeoff(reviewed_pairs, adapters, dataset_version="unit-test-only")
    assert all(not adapter.calls for adapter in adapters)


async def test_rehearsal_suppresses_accuracy_and_readiness(reviewed_pairs, tmp_path):
    adapters = models()
    report = await run_bakeoff(
        reviewed_pairs[:1],
        adapters,
        dataset_version="unit-test-only",
        rehearsal=True,
        output=tmp_path / "rehearsal.json",
    )
    assert report["mode"] == "operational_rehearsal"
    assert not report["scientific_accuracy"] and not report["benchmark_ready"]
    assert not report["dataset_ready"]
    assert report["readiness_issues"]
    assert "single_judge" in report["scope"] and "unadjudicated" in report["scope"]
    for model in report["models"].values():
        assert model["metrics"]["accuracy"] is None
        assert model["metrics"]["admitted_accuracy"] is None
        assert model["metrics"]["raw_severe_false_positive_rate"] is None
        assert model["strata"]["real"]["accuracy"] is None
    assert json.loads((tmp_path / "rehearsal.json").read_text()) == report


async def test_model_identity_uses_vendor_and_model_id(reviewed_pairs):
    adapters = [
        FixtureModel({"judge": judgment().model_dump()}, model_id="same-model", vendor=v)
        for v in ("vendor-1", "vendor-2")
    ]
    report = await run_bakeoff(
        reviewed_pairs[:1], adapters, dataset_version="unit-test-only", rehearsal=True
    )
    assert len(report["models"]) == 2
    assert {m["vendor"] for m in report["models"].values()} == {"vendor-1", "vendor-2"}
    adapters[1].vendor = "  " + adapters[0].vendor.upper() + "  "
    for adapter in adapters:
        adapter.calls.clear()
    with pytest.raises(ValueError, match="distinct vendor/model_id"):
        await run_bakeoff(reviewed_pairs, adapters, dataset_version="unit-test-only")
    assert all(not adapter.calls for adapter in adapters)


async def test_pinned_protocol_and_real_synthetic_strata(reviewed_pairs):
    report = await run_bakeoff(reviewed_pairs, models(), dataset_version="unit-test-only")
    assert report["benchmark_ready"] and report["scientific_accuracy"]
    manifest = protocol_manifest()
    for key in (
        "prompt_sha256",
        "schema_sha256",
        "retrieval_sha256",
        "protocol_sha256",
        "dataset_sha256",
    ):
        assert len(report[key]) == 64
    assert report["protocol_sha256"] == fingerprint(manifest)
    assert manifest["retrieval"]["top_k"] == 8
    for model in report["models"].values():
        assert model["strata"]["real"]["total"] == 30
        assert model["strata"]["synthetic"]["total"] == 10
        assert model["strata"]["unspecified"]["accuracy"] is None


def test_severe_metrics_separate_raw_and_admitted_and_zero_denominators(reviewed_pairs):
    pair = reviewed_pairs[0]
    prediction = Prediction(
        pair_id=pair.id,
        model_id="m",
        model_label="CONTRADICTED",
        admitted_label="NEEDS_REVIEW",
        reason="requires adjudication",
    )
    metrics = summarize([pair], [prediction])
    assert metrics.raw_severe_false_positives == 1
    assert metrics.severe_false_positives == 1
    assert metrics.admitted_severe_false_positives == 0
    assert metrics.raw_severe_false_positive_rate == 1
    assert metrics.admitted_severe_false_positive_rate == 0
    assert metrics.raw_confusion == {"SUPPORTED->CONTRADICTED": 1}
    assert metrics.admitted_confusion == {"SUPPORTED->NEEDS_REVIEW": 1}
    pair.human_label = "CONTRADICTED"
    assert summarize([pair], [prediction]).raw_severe_false_positive_rate is None
    empty = summarize([], [])
    assert empty.accuracy is None and empty.invalid_json_rate is None
    assert empty.quote_verification_failure_rate is None


def test_metrics_reject_partial_coverage_and_mixed_models(reviewed_pairs):
    pairs = reviewed_pairs[:2]
    prediction = Prediction(pair_id=pairs[0].id, model_id="m", reason="fixture")
    with pytest.raises(ValueError, match="exactly once"):
        summarize(pairs, [prediction])
    other = Prediction(pair_id=pairs[1].id, model_id="other-model", reason="fixture")
    with pytest.raises(ValueError, match="one model identity"):
        summarize(pairs, [prediction, other])


async def test_failure_kinds_have_separate_denominators(reviewed_pairs):
    adapters = [
        FixtureModel({"judge": "not JSON"}, model_id="bad-json"),
        FixtureModel({"judge": ModelFailure("fixture failure")}, model_id="offline-fail"),
    ]
    report = await run_bakeoff(
        reviewed_pairs[:1], adapters, dataset_version="unit-test-only", rehearsal=True
    )
    malformed = report["models"]["bad-json"]["metrics"]
    failed = report["models"]["offline-fail"]["metrics"]
    assert malformed["invalid_json_rate"] == 1 and malformed["service_failure_rate"] == 0
    assert failed["service_failure_rate"] == 1 and failed["invalid_json_rate"] == 0
    assert malformed["quote_verification_failure_rate"] is None
    assert failed["quote_verification_failure_rate"] is None


async def test_requires_version_and_explicit_vendor_for_benchmark(reviewed_pairs):
    adapters = models()
    with pytest.raises(ValueError, match="dataset_version"):
        await run_bakeoff(reviewed_pairs, adapters, dataset_version=" ")
    adapters[0].vendor = None
    with pytest.raises(ValueError, match="explicit vendor"):
        await run_bakeoff(reviewed_pairs, adapters, dataset_version="unit-test-only")
    assert all(not adapter.calls for adapter in adapters)


def test_inspect_cli_does_not_create_model_clients(tmp_path, monkeypatch, capsys):
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    monkeypatch.setattr("sys.argv", ["bakeoff", str(path)])
    main()
    report = json.loads(capsys.readouterr().out)
    assert not report["benchmark_ready"] and report["labeled"] == 0


def test_label_cli_rejects_blank_annotator(reviewed_pairs, tmp_path, monkeypatch):
    path = tmp_path / "pairs.jsonl"
    path.write_text(reviewed_pairs[0].model_dump_json())
    monkeypatch.setattr(
        "sys.argv",
        [
            "bakeoff",
            str(path),
            "--label-id",
            reviewed_pairs[0].id,
            "--label",
            "SUPPORTED",
            "--annotator",
            " ",
            "--reason",
            "x",
        ],
    )
    with pytest.raises(SystemExit):
        main()
    assert read_pairs(path)[0].labeled_by == reviewed_pairs[0].labeled_by
