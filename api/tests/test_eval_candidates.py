"""Offline evidence and duplicate checks; no credentials, models or live network."""

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from reportlab.pdfgen import canvas

from api.app.eval import candidates as evaluation
from api.app.eval.candidates import (
    HERE,
    PAPERS,
    Candidate,
    EvidenceSource,
    Proposal,
    canonical_source,
    fetch_evidence,
    normalized,
    pair_key,
    pdf_texts,
    read_jsonl,
    validate_candidates,
    visible_text,
)
from api.app.providers.models import HTTPResult


@pytest.fixture
def dataset(tmp_path):
    pdf_dir = tmp_path / "fixtures/pdfs"
    pdf_dir.mkdir(parents=True)
    cache = tmp_path / "data/evaluation_sources"
    cache.mkdir(parents=True)
    content = b"<p>The measured effect was absent.</p><script>Invented secret evidence</script>"
    (cache / "fixture.html").write_bytes(content)
    source = EvidenceSource(
        id="doi:10.1234/fixture",
        title="Fixture source",
        url="https://example.org/source",
        retrieved_at=datetime.now(UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        cache_key="fixture",
        coverage="ABSTRACT_ONLY",
        format="html",
    )
    rows, proposals = [], []
    for paper in PAPERS:
        path = pdf_dir / f"{paper}.pdf"
        pdf = canvas.Canvas(str(path))
        pdf.drawString(50, 750, "The measured effect was present [1].")
        pdf.drawString(50, 700, "[1] Fixture source.")
        pdf.save()
        row = Candidate(
            id=paper,
            paper_id=paper,
            paper_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            synthetic=paper != PAPERS[0],
            page=1,
            citing_sentence="The measured effect was present [1].",
            citation_marker="[1]",
            cited_reference="[1] Fixture source.",
            source_id=source.id,
            source_quote="The measured effect was absent.",
            source_locator="Abstract",
            quote_role="limiting_context",
        )
        rows.append(row)
        proposals.append(
            Proposal(
                candidate_id=row.id,
                proposed_label="NEEDS_REVIEW",
                reason="Fixture proposal, not a human annotation.",
                author="Codex proposal; not a human annotation",
            )
        )
    return tmp_path, rows, [source], proposals


def checked(dataset, **kwargs):
    root, rows, sources, proposals = dataset
    return validate_candidates(rows, sources, proposals, root=root, expected_count=3, **kwargs)


def test_committed_candidates_are_unlabeled_distinct_and_separate_from_ground_truth():
    rows = read_jsonl(HERE / "candidates.jsonl", Candidate)
    sources = read_jsonl(HERE / "sources.jsonl", EvidenceSource)
    proposals = read_jsonl(HERE / "proposed_labels.jsonl", Proposal)
    assert not validate_candidates(rows, sources, proposals, check_evidence=False)
    assert len(rows) == len({pair_key(row) for row in rows}) == 40
    assert [sum(c.paper_id == paper for c in rows) for paper in PAPERS] == [30, 5, 5]
    assert sum(c.synthetic for c in rows) == 10
    assert all(c.human_label is None and c.labeled_by is None for c in rows)
    assert not (HERE / "pairs.jsonl").read_text().strip()


def test_authentic_fixture_evidence_and_pdf_columns_validate(dataset):
    assert not checked(dataset)
    root, rows, _, _ = dataset
    texts = pdf_texts(root / "fixtures/pdfs" / f"{PAPERS[0]}.pdf")
    assert len(texts) == 3
    assert rows[0].citing_sentence in texts[0]
    assert normalized("a\n b") == "a b"
    assert visible_text(b"<style>hidden</style><p>Visible &amp; real</p>") == "Visible & real"


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"source_quote": "The measured effect was present."}, "inexact source quote"),
        ({"source_quote": "was absent"}, "quote too short"),
        ({"source_quote": "Invented secret evidence is valid."}, "inexact source quote"),
        ({"source_id": "doi:10.1234/missing"}, "missing source receipt"),
        ({"page": 2}, "not on recorded PDF page"),
        ({"paper_sha256": "0" * 64}, "citing PDF hash changed"),
        ({"cited_reference": "Invented reference"}, "reference not in recorded PDF"),
        ({"synthetic": True}, "incorrect synthetic marking"),
        ({"citation_marker": "[2]"}, "marker missing"),
        ({"human_label": "SUPPORTED"}, "human review fields must remain empty"),
        ({"labeled_by": "Codex"}, "human review fields must remain empty"),
    ],
)
def test_rejects_missing_or_altered_evidence_and_false_human_labels(dataset, change, error):
    dataset[1][0] = dataset[1][0].model_copy(update=change)
    assert any(error in message for message in checked(dataset))


def test_rejects_duplicate_pairs_despite_new_id_whitespace_and_identifier_alias(dataset):
    _, rows, _, _ = dataset
    rows[1] = rows[0].model_copy(
        update={
            "id": rows[1].id,
            "citing_sentence": "  THE measured\n effect was present [1].",
            "source_id": "https://doi.org/10.1234/FIXTURE",
        }
    )
    assert any("duplicate claim-source pair" in message for message in checked(dataset))
    assert canonical_source("https://arxiv.org/pdf/1706.03762v7.pdf") == "arxiv:1706.03762"
    assert canonical_source("https://arxiv.org/pdf/1706.03762.pdf") == "arxiv:1706.03762"


def test_rejects_duplicate_ids_sources_and_incomplete_proposals(dataset):
    dataset[1][1].id = dataset[1][0].id
    dataset[2].append(dataset[2][0])
    dataset[3].pop()
    errors = checked(dataset)
    assert any("duplicate candidate ID" in message for message in errors)
    assert any("duplicate source identifier" in message for message in errors)
    assert any("proposals must cover" in message for message in errors)


def test_missing_files_and_changed_receipts_fail_offline(dataset):
    root, _, sources, _ = dataset
    path = root / "data/evaluation_sources/fixture.html"
    path.write_bytes(b"changed")
    assert any("evidence hash changed" in message for message in checked(dataset))
    path.unlink()
    assert any("missing evidence" in message for message in checked(dataset))
    (root / f"fixtures/pdfs/{PAPERS[0]}.pdf").unlink()
    assert any("missing citing PDF" in message for message in checked(dataset))
    assert not checked(dataset, check_evidence=False)
    assert sources[0].coverage == "ABSTRACT_ONLY"


def test_pdf_source_requires_correct_recorded_page(dataset):
    root, rows, sources, _ = dataset
    source = sources[0]
    source.format = "fixture_pdf"
    source.cache_key = PAPERS[0]
    source.sha256 = rows[0].paper_sha256
    source.coverage = "FULL_TEXT"
    for row in rows:
        row.source_quote = row.citing_sentence
        row.source_locator = "PDF page 1, test"
    assert not checked(dataset)
    rows[0].source_locator = "PDF page 2, test"
    assert any("inexact source quote" in message for message in checked(dataset))
    rows[0].source_locator = "Abstract"
    assert any("inexact source quote" in message for message in checked(dataset))


def test_malformed_pdf_is_reported_as_missing_verifiable_evidence(dataset):
    root, rows, sources, _ = dataset
    path = root / f"fixtures/pdfs/{PAPERS[0]}.pdf"
    path.write_bytes(b"not a PDF")
    assert pdf_texts(path) == []
    sources[0].format = "fixture_pdf"
    sources[0].cache_key = PAPERS[0]
    sources[0].sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    rows[0].paper_sha256 = sources[0].sha256
    errors = checked(dataset)
    assert any("unreadable source PDF" in message for message in errors)
    assert any("not on recorded PDF page" in message for message in errors)


def test_schema_rejects_empty_quotes_path_traversal_and_misplaced_proposals(dataset, tmp_path):
    _, rows, sources, _ = dataset
    with pytest.raises(ValidationError):
        Candidate.model_validate({**rows[0].model_dump(), "source_quote": ""})
    with pytest.raises(ValidationError):
        EvidenceSource.model_validate({**sources[0].model_dump(), "cache_key": "../../.env"})
    with pytest.raises(ValidationError):
        Candidate.model_validate({**rows[0].model_dump(), "proposed_label": "SUPPORTED"})
    path = tmp_path / "rows.jsonl"
    path.write_text(rows[0].model_dump_json() + "\n\n")
    assert read_jsonl(path, Candidate) == [rows[0]]


@pytest.mark.parametrize(
    "response", [HTTPResult(status=503), HTTPResult(status=200, content=b"changed")]
)
async def test_anonymous_refetch_does_not_overwrite_changed_receipts(
    dataset, monkeypatch, response
):
    root, _, sources, _ = dataset
    path = root / "data/evaluation_sources/fixture.html"
    original = path.read_bytes()
    path.unlink()

    class AnonymousGateway:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def safe_fetch(self, url):
            assert url == sources[0].url
            return response

    monkeypatch.setattr(evaluation, "Gateway", AnonymousGateway)
    assert await fetch_evidence(sources, root)
    assert not path.exists()
    response.status, response.content = 200, original
    assert not await fetch_evidence(sources, root)
    assert path.read_bytes() == original
    assert not await fetch_evidence(sources, root)


def test_cli_reports_schema_errors_without_network(tmp_path, monkeypatch, capsys):
    (tmp_path / "candidates.jsonl").write_text('{"source_quote": ""}\n')
    monkeypatch.setattr(evaluation, "HERE", tmp_path)
    monkeypatch.setattr("sys.argv", ["candidates"])
    with pytest.raises(SystemExit) as result:
        evaluation.main()
    assert result.value.code == 1
    assert '"valid": false' in capsys.readouterr().out
