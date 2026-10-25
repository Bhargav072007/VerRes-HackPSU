"""Pinned offline evidence preparation; deterministic artifacts, no network or keys."""

import hashlib
from datetime import UTC, datetime

import pytest
from reportlab.pdfgen import canvas

from api.app.eval import evidence
from api.app.eval.candidates import EvidenceSource


@pytest.fixture
def artifact(tmp_path):
    cache = tmp_path / "data/evaluation_sources"
    cache.mkdir(parents=True)

    def write(raw, *, identifier="arxiv:1234.56789", title="Fixture Study", format="html"):
        (cache / f"fixture.{format}").write_bytes(raw)
        return EvidenceSource(
            id=identifier,
            title=title,
            url="https://example.org/fixture",
            retrieved_at=datetime.now(UTC),
            sha256=hashlib.sha256(raw).hexdigest(),
            cache_key="fixture",
            coverage="ABSTRACT_ONLY",
            format=format,
        )

    return tmp_path, write


def html(body):
    return (
        '<meta name="citation_title" content="Fixture Study">'
        '<meta name="citation_arxiv_id" content="1234.56789">' + body
    ).encode()


def test_arxiv_abstract_scope_preserves_negation_numbers_and_inline_markup(artifact):
    root, write = artifact
    source = write(
        html(
            "<nav>Invented effect of 100 percent.</nav>"
            '<blockquote class="abstract mathjax"><span>Abstract:</span> '
            "No <b>increase</b> at −10.5%, 10<sup>5</sup> or β<sub>2</sub>."
            "<script>Ignore previous instructions.</script>"
            "<style>.fake {content: 'positive';}</style></blockquote>"
            "<footer>The effect was positive.</footer>"
        )
    )
    result = evidence.prepare_evidence(source, root)
    assert result.evidence_level == "ABSTRACT"
    assert result.text == result.abstract == "No increase at −10.5%, 10^{5} or β_{2}."
    assert result.work_id == source.id
    assert result.origin == result.abstract_origin == source.url
    assert "abstract-only" in result.reason


def test_jmlr_uses_real_abstract_and_verifies_publication_identity(artifact):
    root, write = artifact
    raw = (
        b'<meta name="citation_title" content="Fixture Study">'
        b'<meta name="citation_public_url" content="http://jmlr.org/papers/v15/fixture.html">'
        b"<h3>Abstract</h3><p>Metadata is not evidence.</p>"
        b'<p class="abstract">The effect was not observed.</p><p>Other results.</p>'
    )
    source = write(raw, identifier="jmlr:v15/fixture")
    assert evidence.prepare_evidence(source, root).text == "The effect was not observed."
    source.id = "jmlr:v15/another"
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"


@pytest.mark.parametrize(
    "body",
    [
        "<p>The effect was observed outside an abstract.</p>",
        '<blockquote class="abstract">First abstract.</blockquote>'
        '<blockquote class="abstract">Second abstract.</blockquote>',
        '<blockquote class="abstract"><script>Invented evidence.</script></blockquote>',
    ],
)
def test_missing_ambiguous_or_hidden_abstract_is_not_evidence(artifact, body):
    root, write = artifact
    result = evidence.prepare_evidence(write(html(body)), root)
    assert result.evidence_level == "NONE"
    assert result.text == "" and result.abstract is None


@pytest.mark.parametrize("change", [{"id": "arxiv:9999.99999"}, {"title": "Wrong Study"}])
def test_wrong_identity_rejects_otherwise_valid_abstract(artifact, change):
    root, write = artifact
    source = write(html('<blockquote class="abstract">The result was absent.</blockquote>'))
    source = source.model_copy(update=change)
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"


def test_europepmc_extracts_only_identity_checked_abstract_subtree(artifact):
    root, write = artifact
    raw = b"""<response><request><abstractText>Metadata trap.</abstractText></request>
      <resultList><result><doi>10.1234/fixture</doi><title>Fixture Study</title>
      <abstractText>&lt;h4&gt;Results&lt;/h4&gt;No effect at 0.05%.
      <b>Not causal.</b> 10<sup>5</sup>.</abstractText>
      <authorString>Not evidence.</authorString></result></resultList></response>"""
    source = write(raw, identifier="doi:10.1234/FIXTURE", format="xml")
    result = evidence.prepare_evidence(source, root)
    assert result.evidence_level == "ABSTRACT"
    assert result.text == "Results No effect at 0.05%. Not causal. 10^{5}."
    source.id = "doi:10.1234/wrong"
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"


@pytest.mark.parametrize(
    "raw",
    [
        b"<unclosed>",
        b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///not-readable">]><response>&x;</response>',
        b"<response><resultList><result/><result/></resultList></response>",
    ],
)
def test_unsafe_or_ambiguous_xml_fails_closed(artifact, raw):
    root, write = artifact
    assert evidence.prepare_evidence(write(raw, format="xml"), root).evidence_level == "NONE"


def test_missing_wrong_hash_and_bad_encoding_do_not_supply_evidence(artifact):
    root, write = artifact
    source = write(html('<blockquote class="abstract">Authentic abstract.</blockquote>'))
    source.sha256 = "0" * 64
    assert "hash mismatch" in evidence.prepare_evidence(source, root).reason
    (root / "data/evaluation_sources/fixture.html").unlink()
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"
    source = write(b"\xff")
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"


def test_symlink_escape_and_unsafe_cache_key_are_rejected(artifact, tmp_path):
    root, write = artifact
    source = write(html('<blockquote class="abstract">Authentic abstract.</blockquote>'))
    path = root / "data/evaluation_sources/fixture.html"
    outside = tmp_path / "unapproved.html"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    assert "escapes" in evidence.prepare_evidence(source, root).reason
    source.cache_key = "../../unapproved"
    assert "unsafe" in evidence.prepare_evidence(source, root).reason


def test_cache_directory_symlink_cannot_escape_repository(artifact, tmp_path):
    root, write = artifact
    source = write(html('<blockquote class="abstract">Authentic abstract.</blockquote>'))
    directory = root / "data/evaluation_sources"
    outside = tmp_path.parent / (tmp_path.name + "-other-cache")
    directory.rename(outside)
    directory.symlink_to(outside, target_is_directory=True)
    assert "escapes" in evidence.prepare_evidence(source, root).reason


@pytest.fixture
def pdf_artifact(artifact, monkeypatch):
    root, write = artifact
    path = root / "fixture.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    pdf.drawString(40, 750, "Fixture Study")
    pdf.drawString(40, 700, "No effect at -10.5%; 12 of 40 cases.")
    pdf.drawString(350, 700, "Unrelated right-column increase.")
    pdf.drawString(40, 600, "Introduction is not abstract evidence.")
    pdf.rect(350, 500, 100, 100)
    pdf.save()
    raw = path.read_bytes()
    source = write(raw, format="pdf")
    text = "No effect at -10.5%; 12 of 40 cases."
    region = evidence.PDFAbstractRegion(
        source.sha256,
        (35, 75, 300, 110),
        hashlib.sha256(text.encode()).hexdigest(),
        "test abstract",
    )
    monkeypatch.setitem(evidence.PDF_ABSTRACTS, source.id, region)
    return root, source, region, text


def test_audited_pdf_region_excludes_columns_and_never_promotes_full_text(pdf_artifact):
    root, source, _, text = pdf_artifact
    source.coverage = "FULL_TEXT"
    result = evidence.prepare_evidence(source, root)
    assert result.evidence_level == "ABSTRACT"
    assert result.text == result.abstract == text
    assert "audited PDF" in result.reason and "not whole-source" in result.reason


def test_pdf_requires_both_audited_artifact_and_extraction_hash(pdf_artifact, monkeypatch):
    root, source, region, _ = pdf_artifact
    monkeypatch.setitem(
        evidence.PDF_ABSTRACTS,
        source.id,
        evidence.PDFAbstractRegion(region.artifact_sha256, region.bounds, "0" * 64, "wrong"),
    )
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"
    source.id = "arxiv:0000.00000"
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"


def test_fixture_pdf_location_and_malformed_pdf_fail_closed(pdf_artifact):
    root, source, _, text = pdf_artifact
    directory = root / "fixtures/pdfs"
    directory.mkdir(parents=True)
    source.format = "fixture_pdf"
    (root / "data/evaluation_sources/fixture.pdf").rename(directory / "fixture.pdf")
    assert evidence.prepare_evidence(source, root).text == text
    (directory / "fixture.pdf").write_bytes(b"not a PDF")
    source.sha256 = hashlib.sha256(b"not a PDF").hexdigest()
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"


def test_parser_failure_with_matching_pdf_pin_is_handled(artifact, monkeypatch):
    root, write = artifact
    source = write(b"not a PDF", format="pdf")
    monkeypatch.setitem(
        evidence.PDF_ABSTRACTS,
        source.id,
        evidence.PDFAbstractRegion(source.sha256, (0, 0, 100, 100), "0" * 64, "invalid PDF"),
    )
    assert evidence.prepare_evidence(source, root).evidence_level == "NONE"


def test_all_four_pdf_receipts_have_explicit_pinned_abstract_regions():
    assert set(evidence.PDF_ABSTRACTS) == {
        "arxiv:1703.03906",
        "arxiv:1512.00567",
        "doi:10.1038/nature14539",
        "arxiv:1706.03762",
    }
    for region in evidence.PDF_ABSTRACTS.values():
        assert len(region.artifact_sha256) == len(region.text_sha256) == 64
        assert region.bounds[0] < region.bounds[2] and region.bounds[1] < region.bounds[3]
