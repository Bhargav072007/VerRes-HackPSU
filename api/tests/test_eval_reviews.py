"""Human-review/export integrity using a clearly synthetic local 40-row corpus."""

import hashlib
import json
from datetime import UTC, datetime

import pytest
from reportlab.pdfgen import canvas

from api.app.eval import execution, rehearsal, reviews
from api.app.eval.bakeoff import dataset_readiness
from api.app.eval.candidates import PAPERS, Candidate, EvidenceSource, read_jsonl
from api.app.eval.reviews import (
    HumanReview,
    export_reviewed,
    jsonl,
    load_corpus,
    prepare_bundle,
    record_hash,
    review_issues,
    review_packet,
    review_template,
    reviewed_pairs,
    verify_export,
)


@pytest.fixture
def corpus(tmp_path):
    here = tmp_path / "eval"
    here.mkdir()
    cache = tmp_path / "data/evaluation_sources"
    cache.mkdir(parents=True)
    html = (
        b'<meta name="citation_title" content="Fixture Source">'
        b'<meta name="citation_arxiv_id" content="2401.12345">'
        b'<blockquote class="abstract mathjax">Abstract:The treatment did not improve '
        b"outcomes in the trial.</blockquote><p>Unrelated page chrome is not evidence.</p>"
    )
    (cache / "fixture.html").write_bytes(html)
    source = EvidenceSource(
        id="arxiv:2401.12345",
        title="Fixture Source",
        url="https://arxiv.org/abs/2401.12345",
        retrieved_at=datetime.now(UTC),
        sha256=hashlib.sha256(html).hexdigest(),
        cache_key="fixture",
        coverage="ABSTRACT_ONLY",
        format="html",
    )
    pdfs = tmp_path / "fixtures/pdfs"
    pdfs.mkdir(parents=True)
    candidates = []
    for paper, count in zip(PAPERS, (30, 5, 5), strict=True):
        path = pdfs / f"{paper}.pdf"
        pdf = canvas.Canvas(str(path))
        sentences = [f"Fixture claim {i} reports no effect [1]." for i in range(count)]
        for i, sentence in enumerate(sentences):
            pdf.drawString(50, 750 - 15 * i, sentence)
        pdf.drawString(50, 100, "[1] Fixture Source.")
        pdf.save()
        for sentence in sentences:
            candidates.append(
                Candidate(
                    id=f"fixture-{len(candidates) + 1:02d}",
                    paper_id=paper,
                    paper_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    synthetic=paper != PAPERS[0],
                    page=1,
                    citing_sentence=sentence,
                    citation_marker="[1]",
                    cited_reference="[1] Fixture Source.",
                    source_id=source.id,
                    source_quote="did not improve outcomes in the trial",
                    source_locator="Abstract",
                    quote_role="supporting_context",
                )
            )
    (here / "candidates.jsonl").write_text(jsonl(candidates))
    (here / "sources.jsonl").write_text(jsonl([source]))
    # Any accidental proposal read fails JSON parsing: it is not needed by blind tooling.
    (here / "proposed_labels.jsonl").write_text("PROPOSALS MUST NOT BE READ")
    return tmp_path, here


def approved_fixture(corpus):
    root, here = corpus
    candidates, sources, prepared = load_corpus(root=root, here=here)
    rows = review_template(candidates, sources, prepared)
    for candidate, review in zip(candidates, rows, strict=True):
        review.annotation_status = "APPROVED"
        review.citation_function = "SPECIFIC_CLAIM"
        review.claim = {
            "text": candidate.citing_sentence,
            "subject_or_population": "Synthetic test subjects",
            "exposure_or_intervention": None,
            "outcome": "Synthetic fixture outcome",
            "direction": "no effect",
            "magnitude": None,
            "relation": "descriptive",
            "hedge": "definite",
            "scope_or_time": None,
        }
        review.human_label = "SUPPORTED"
        review.labeled_by = "Explicit synthetic unit-test annotator"
        review.label_reason = "Synthetic fixture only; never real ground truth."
        review.evidence_quote = candidate.source_quote
        review.source_identity = "MATCH"
        review.human_attestation = True
        review.reviewed_at = "2026-10-24T12:00:00+00:00"
    return candidates, sources, prepared, rows


def test_prepare_is_blind_null_and_never_initializes_gateway(corpus, monkeypatch):
    from api.app.providers.http import Gateway

    monkeypatch.setattr(
        Gateway, "__init__", lambda *_args, **_kwargs: pytest.fail("network initialized")
    )
    root, here = corpus
    output = root / "packet"
    manifest = prepare_bundle(output, root=root, here=here)
    rows = read_jsonl(output / "reviews.jsonl", HumanReview)
    assert len(rows) == manifest["candidate_count"] == 40
    assert manifest["human_labeled"] == 0 and not manifest["benchmark_ready"]
    assert all(r.human_label is None and r.labeled_by is None and r.claim is None for r in rows)
    assert all(not r.human_attestation for r in rows)
    assert "proposed_label" not in (output / "review.html").read_text()
    with pytest.raises(ValueError, match="not empty"):
        prepare_bundle(output, root=root, here=here)


def test_committed_template_is_unannotated_and_bound_to_candidate_receipts():
    from api.app.eval.candidates import HERE, canonical_source

    candidates = read_jsonl(HERE / "candidates.jsonl", Candidate)
    sources = read_jsonl(HERE / "sources.jsonl", EvidenceSource)
    template = read_jsonl(HERE / "review_template.jsonl", HumanReview)
    source_map = {canonical_source(s.id): s for s in sources}
    assert len(template) == len(candidates) == 40
    for row, candidate in zip(template, candidates, strict=True):
        assert row.candidate_id == candidate.id
        assert row.candidate_sha256 == record_hash(candidate)
        assert row.source_receipt_sha256 == record_hash(
            source_map[canonical_source(candidate.source_id)]
        )
        assert row.annotation_status == "PENDING" and not row.human_attestation
        assert row.human_label is None and row.labeled_by is None and row.claim is None


def test_export_refuses_pending_records_and_does_not_create_output(corpus):
    root, here = corpus
    candidates, sources, prepared = load_corpus(root=root, here=here)
    rows = review_template(candidates, sources, prepared)
    review_path = root / "pending.jsonl"
    review_path.write_text(jsonl(rows))
    output = root / "rejected"
    with pytest.raises(ValueError, match="PENDING"):
        export_reviewed(review_path, output, root=root, here=here)
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("candidate_sha256", "0" * 64, "stale candidate"),
        ("source_receipt_sha256", "0" * 64, "stale source_receipt"),
        ("prepared_source_sha256", "0" * 64, "stale prepared_source"),
        ("human_attestation", False, "attestation"),
        ("labeled_by", "Codex", "human annotator"),
        ("label_reason", " ", "label or reason"),
        ("human_label", None, "label or reason"),
        ("claim", None, "atomic claim"),
        ("reviewed_at", "2026-10-24T12:00:00", "timezone-aware"),
        ("citation_function", None, "citation function"),
        ("source_identity", None, "source identity"),
        ("evidence_quote", "The treatment improved outcomes substantially.", "quote absent"),
        ("source_identity", "UNCERTAIN", "uncertain source identity"),
    ],
)
def test_review_export_rejects_unreviewed_or_stale_inputs(corpus, field, value, message):
    candidates, sources, prepared, rows = approved_fixture(corpus)
    setattr(rows[0], field, value)
    assert any(message in s for s in review_issues(candidates, sources, prepared, rows))


def test_duplicate_reviews_and_source_change_invalidate_annotations(corpus):
    candidates, sources, prepared, rows = approved_fixture(corpus)
    assert not review_issues(candidates, sources, prepared, rows)
    assert review_issues(candidates, sources, prepared, rows + [rows[0]])
    sources[0].title = "Changed source"
    assert any(
        "stale source_receipt" in s for s in review_issues(candidates, sources, prepared, rows)
    )


def test_reviewed_export_is_versioned_and_bound_to_unchanged_evidence(corpus):
    root, here = corpus
    candidates, sources, prepared, rows = approved_fixture(corpus)
    pairs = reviewed_pairs(candidates, sources, prepared, rows)
    assert not dataset_readiness(pairs)
    assert sum(p.synthetic for p in pairs) == 10
    assert all(p.source.evidence_level == "ABSTRACT" for p in pairs)
    review_path = root / "reviewed.jsonl"
    review_path.write_text(jsonl(rows))
    output = root / "export-v1"
    manifest = export_reviewed(review_path, output, root=root, here=here)
    assert manifest["benchmark_ready"]
    assert verify_export(output, review_path, root=root, here=here) == pairs
    assert (output / "reviews.jsonl").read_bytes() == review_path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        export_reviewed(review_path, output, root=root, here=here)
    modified = dict(manifest, candidate_set_sha256="0" * 64)
    (output / "manifest.json").write_text(json.dumps(modified))
    with pytest.raises(ValueError, match="no longer matches"):
        verify_export(output, review_path, root=root, here=here)
    (output / "manifest.json").write_text(json.dumps(manifest))
    (output / "pairs.jsonl").write_text(jsonl(pairs) + "\n")
    with pytest.raises(ValueError, match="pair file hash"):
        verify_export(output, review_path, root=root, here=here)


def test_review_packet_flags_coverage_and_math_without_proposed_labels(corpus):
    candidates, sources, prepared, _ = approved_fixture(corpus)
    candidates[0].id = "bc-eval-022"
    candidates[0].source_quote = "A body-only quote is absent from this abstract."
    sources[0].coverage = "FULL_TEXT"
    packet = review_packet(candidates, sources, prepared)
    assert packet[0]["prepared_scope"] == "ABSTRACT_ONLY"
    assert not packet[0]["initial_quote_in_prepared_source"]
    assert len(packet[0]["review_flags"]) >= 3
    assert "quote_role" not in packet[0] and "human_label" not in packet[0]
    assert record_hash(candidates[0]) != record_hash(sources[0])


async def test_fixture_rehearsal_has_zero_scientific_accuracy_or_external_access(
    corpus, monkeypatch
):
    root, here = corpus
    original = load_corpus(root=root, here=here)
    monkeypatch.setattr(rehearsal, "load_corpus", lambda: original)
    report = await rehearsal.rehearse(root / "fixture-run.json")
    assert report["operational_checks"]["candidate_inputs"] == 40
    assert report["operational_checks"]["local_fixture_calls"] == 80
    assert report["operational_checks"]["paid_model_calls"] == 0
    assert not report["scientific_accuracy"] and not report["dataset_ready"]
    assert all(m["metrics"]["accuracy"] is None for m in report["models"].values())
    assert report["models"]["offline-fault-injection-v1"]["metrics"]["invalid_json_rate"] == 0.2
    with pytest.raises(ValueError, match="already exists"):
        await rehearsal.rehearse(root / "fixture-run.json")
    with pytest.raises(ValueError, match="only exercises"):
        await rehearsal.OfflineFixtureModel().complete(task="unknown")


async def test_live_driver_requires_authorization_and_validated_export(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(execution, "verify_export", lambda *_: calls.append("verified") or [])

    async def run(*_args, **_kwargs):
        calls.append("models")
        return {"fixture": True}

    monkeypatch.setattr(execution, "run_bakeoff", run)
    args = (tmp_path / "export", tmp_path / "reviews", [])
    with pytest.raises(ValueError, match="authorization"):
        await execution.run_reviewed_bakeoff(*args, dataset_version="v1", output=tmp_path / "run")
    assert not calls
    with pytest.raises(ValueError, match="authorization"):
        await execution.run_reviewed_bakeoff(
            *args, dataset_version="v1", output=tmp_path / "run", live_calls_authorized="false"
        )
    assert await execution.run_reviewed_bakeoff(
        *args, dataset_version="v1", output=tmp_path / "run", live_calls_authorized=True
    ) == {"fixture": True}
    assert calls == ["verified", "models"]


def test_legacy_cli_cannot_relabel_provenance_bound_pairs(corpus, monkeypatch):
    from api.app.eval import bakeoff

    root, _ = corpus
    pairs = reviewed_pairs(*approved_fixture(corpus))
    path = root / "exported.jsonl"
    path.write_text(jsonl(pairs))
    original = path.read_bytes()
    monkeypatch.setattr(
        "sys.argv",
        [
            "bakeoff",
            str(path),
            "--label-id",
            pairs[0].id,
            "--label",
            "CONTRADICTED",
            "--annotator",
            "Example reviewer",
            "--reason",
            "Changed",
        ],
    )
    with pytest.raises(SystemExit):
        bakeoff.main()
    assert path.read_bytes() == original


def test_status_cli_reports_pending_without_models(corpus, monkeypatch, capsys):
    root, here = corpus
    prepared = load_corpus(root=root, here=here)
    rows = review_template(*prepared)
    path = root / "pending.jsonl"
    path.write_text(jsonl(rows))
    monkeypatch.setattr(reviews, "load_corpus", lambda: prepared)
    monkeypatch.setattr("sys.argv", ["reviews", "status", str(path)])
    reviews.main()
    result = json.loads(capsys.readouterr().out)
    assert not result["benchmark_ready"] and result["approved"] == 0
