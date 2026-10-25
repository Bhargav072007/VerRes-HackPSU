"""Replay the eight ambiguous candidate sets exported from fresh Attention run.

Venue names are enriched from anonymous public Crossref DOI receipts. Full vs
family-name authors are preserved; the production path still uses provider flags.
"""

import json
from pathlib import Path

import pytest

from api.app.providers.boundary import parsed_reference
from api.app.providers.models import Work
from api.app.resolve.existence import compare_author, same_candidate
from api.app.resolve.service import ResolveService
from api.tests.test_shared_interfaces import provider
from contracts.schema import Reference

ROWS = [
    json.loads(line)
    for line in (Path(__file__).parent / "fixtures/paper1-ambiguous-candidates.jsonl")
    .read_text()
    .splitlines()
]


@pytest.mark.parametrize("row", ROWS, ids=[r["reference"]["id"] for r in ROWS])
async def test_eight_real_search_candidate_sets_resolve_without_duplicate_ties(row):
    works = [Work.model_validate(w) for w in row["works"]]
    reference = Reference.model_validate(row["reference"])
    result = await ResolveService(
        provider("crossref", [w for w in works if w.provider == "crossref"]),
        provider("openalex", [w for w in works if w.provider == "openalex"]),
    ).resolve_reference(reference)
    assert result.status == "VERIFIED", (
        reference.id,
        result.reason,
        parsed_reference(reference).venue,
    )
    assert result.matched_reference.doi == row["works"][0]["doi"]


def test_one_doi_different_author_formats_is_one_candidate():
    left = Work(
        provider="crossref",
        id="x",
        doi="10.1234/a",
        title="A study",
        authors=["de Vries"],
        year=2024,
    )
    right = left.model_copy(
        update={
            "provider": "openalex",
            "authors": ["Johannes de Vries"],
            "author_names_are_full": True,
        }
    )
    assert same_candidate(left, right)
    assert not same_candidate(left, right.model_copy(update={"authors": ["Johannes Smith"]}))
    assert not same_candidate(left, right.model_copy(update={"year": 1990}))
    assert not same_candidate(left, right.model_copy(update={"doi": "10.1234/b"}))


def test_middle_initial_in_reference_surname_can_match_structured_family():
    reference = Reference(id="b", raw_text="", authors=["Mitchell P Marcus"])
    work = Work(provider="crossref", id="x", authors=["Marcus"])
    assert compare_author(parsed_reference(reference), work) is True
    reference.authors = ["de Vries"]
    work.authors = ["Vries"]
    assert compare_author(parsed_reference(reference), work) is False
