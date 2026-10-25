"""Offline replay of public demo references + arXiv metadata fetched 2026-10-25.

The planted-reference fixture remains synthetic. arXiv receipts contain only
bibliographic metadata, not downloaded abstract/full-text evidence.
"""

import json
from pathlib import Path

import httpx
import pytest

from api.app.ingest.tei import identifiers, parse_tei
from api.app.providers.boundary import parsed_reference, reference_kind
from api.app.providers.http import Gateway
from api.app.providers.identifiers import extract_arxiv, normalize_arxiv, same_arxiv
from api.app.providers.metadata import Arxiv
from api.app.providers.models import Work
from api.app.resolve.service import ResolveService
from api.tests.test_shared_interfaces import provider
from contracts.schema import Reference

FIXTURES = Path(__file__).parent / "fixtures"
REFERENCES = [
    json.loads(line) for line in (FIXTURES / "demo-arxiv-references.jsonl").read_text().splitlines()
]
WORKS = [
    Work.model_validate_json(line)
    for line in (FIXTURES / "demo-arxiv-metadata.jsonl").read_text().splitlines()
]


@pytest.mark.parametrize(
    "row", REFERENCES, ids=[r["paper"] + "-" + r["reference"]["id"] for r in REFERENCES]
)
async def test_demo_arxiv_identifiers_bypass_fuzzy_candidates(row):
    reference = Reference.model_validate(row["reference"])
    arxiv = parsed_reference(reference).arxiv
    work = next(w for w in WORKS if same_arxiv(arxiv, w.arxiv))
    crossref, alex = provider("crossref", []), provider("openalex", [])
    result = await ResolveService(
        crossref, alex, arxiv=provider("arxiv", [work])
    ).resolve_reference(reference)
    assert result.status == "VERIFIED", result.reason
    assert same_arxiv(arxiv, result.matched_reference.arxiv_id)
    crossref.search.assert_not_awaited()
    alex.search.assert_not_awaited()


@pytest.mark.parametrize(
    "value",
    [
        "1706.03762v2",
        "arXiv:1706.03762v2",
        "https://arxiv.org/abs/1706.03762v2",
        "https://arxiv.org/pdf/1706.03762v2.pdf",
        "https://doi.org/10.48550/arXiv.1706.03762v2",
    ],
)
def test_canonical_arxiv_forms(value):
    assert normalize_arxiv(value) == "1706.03762v2"


@pytest.mark.parametrize(
    "value",
    [
        "../../etc/passwd",
        "https://evil.org/abs/1706.03762",
        "1706.03762?query=1",
        "1706.03762/extra",
        None,
    ],
)
def test_invalid_arxiv_forms(value):
    assert normalize_arxiv(value) is None


def test_raw_corr_and_legacy_identifiers():
    assert identifiers("CoRR, abs/1409.0473, 2014.")["arxiv"] == "1409.0473"
    assert extract_arxiv("arXiv:math.GT/0309136v2") == "math.gt/0309136v2"
    assert same_arxiv("1706.03762", "1706.03762v7")
    assert not same_arxiv("1706.03762v2", "1706.03762v3")
    assert not same_arxiv("1706.03762", "1810.04805")


def test_tei_explicit_idno_is_normalized(tei):
    paper = parse_tei(tei.replace(b"2401.12345", b"arXiv:2401.12345")).paper
    assert paper.references[0].arxiv == "2401.12345"


async def test_atom_boundary_accepts_normalized_id():
    body = (
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        b"<id>https://arxiv.org/abs/1706.03762v7</id>"
        b"<title>Attention Is All You Need</title>"
        b"<published>2017-06-12</published></entry></feed>"
    )
    async with Gateway(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    ) as gateway:
        result = await Arxiv(gateway).lookup("arXiv:1706.03762")
        assert result.definitive and result.works[0].arxiv == "1706.03762v7"


@pytest.mark.parametrize(
    "changes", [{"arxiv": "1810.04805"}, {"title": "An unrelated invented title"}, {"year": 1990}]
)
async def test_direct_identifier_does_not_hide_metadata_or_id_conflicts(changes):
    reference = Reference.model_validate(REFERENCES[-1]["reference"])
    work = next(w for w in WORKS if same_arxiv(parsed_reference(reference).arxiv, w.arxiv))
    result = await ResolveService(
        provider("crossref", []),
        provider("openalex", []),
        arxiv=provider("arxiv", [work.model_copy(update=changes)]),
    ).resolve_reference(reference)
    assert result.status == "AMBIGUOUS"


@pytest.mark.parametrize("definitive,status", [(True, "NOT_FOUND"), (False, "CHECK_INCOMPLETE")])
async def test_planted_ref_is_not_found_only_when_all_providers_answer(definitive, status):
    fixture = json.loads((FIXTURES / "planted-reference-resolution.json").read_text())
    assert fixture["synthetic"] is True
    reference = Reference.model_validate(fixture["reference"])
    candidates = [
        Work(
            provider="crossref",
            id=c["doi"] or c["id"],
            doi=c["doi"],
            title=c["title"],
            authors=c["authors"],
            year=c["year"],
        )
        for c in fixture["candidates"]
    ]
    assert reference_kind(reference) == "journal-article"
    result = await ResolveService(
        provider("crossref", candidates), provider("openalex", [], definitive=definitive)
    ).resolve_reference(reference)
    assert result.status == status


@pytest.mark.parametrize(
    "tail,kind",
    [
        ("Academic Press, 14(3), 211-229.", "book"),
        ("https://example.org (accessed 2024).", "website"),
        ("Unspecified venue.", "unknown"),
    ],
)
def test_coverage_is_not_inferred_from_title_or_doi_alone(tail, kind):
    reference = Reference(
        id="b",
        raw_text="A sufficiently long citation title. " + tail,
        title="A sufficiently long citation title",
        authors=["Smith"],
        year=2021,
    )
    assert reference_kind(reference) == kind
