import pytest

from api.app.eval.bakeoff import EvalPair, run_bakeoff
from api.app.providers.boundary import work_reference
from api.app.providers.http import Gateway
from api.app.providers.models import ProviderResult, Work
from api.app.resolve.service import ResolveService
from api.app.sources.service import SourceService
from api.tests.helpers import FixtureModel
from api.tests.test_shared_interfaces import provider
from contracts.schema import EvidenceLevel, ExistenceResult, Reference, RetractionStatus


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "http://example.org/a", "https://user:password@example.org/a"]
)
def test_public_reference_never_exposes_unsafe_provider_urls(url):
    work = Work(provider="openalex", id="W1", oa_url=url)
    assert work_reference(work, "b1").url is None


async def test_invalid_doi_is_not_hidden_by_a_good_bibliographic_match():
    reference = Reference(
        id="b1",
        raw_text="An extended scientific title",
        title="An extended scientific title",
        authors=["Smith"],
        year=2024,
        doi="invalid",
    )
    work = Work(
        provider="crossref",
        id="10.1234/a",
        doi="10.1234/a",
        title=reference.title,
        authors=reference.authors,
        year=2024,
    )
    crossref, openalex = provider("crossref", [work]), provider("openalex", [work])
    for client in (crossref, openalex):
        client.lookup.return_value = ProviderResult(provider="fixture", definitive=False)
    result = await ResolveService(crossref, openalex).resolve_reference(reference)
    assert result.status == "VERIFIED_WITH_DISCREPANCIES" and result.discrepancies
    assert result.matched_reference.doi == "10.1234/a"


async def test_misaligned_matched_reference_is_not_used_for_source_or_retraction():
    existence = ExistenceResult(
        reference_id="b1",
        status="VERIFIED",
        matched_reference=Reference(id="wrong", raw_text="Paper"),
        reason="fixture",
    )
    async with Gateway() as gateway:
        source = await SourceService(gateway).fetch_source(existence)
    assert (
        source.evidence_level == EvidenceLevel.METADATA_ONLY and source.status == "CHECK_INCOMPLETE"
    )
    result = await ResolveService(None, None).check_retraction(existence, None)
    assert result.status == RetractionStatus.UNKNOWN


async def test_abstention_is_not_reported_as_a_fabricated_quote(claim, source):
    pair = EvalPair(id="p1", paper_id="p", citation_text=claim.text, claim=claim, source=source)
    response = {
        "label": "NEEDS_REVIEW",
        "reason": "insufficient source evidence",
        "evidence_strength": "INSUFFICIENT",
        "evidence": [],
        "mismatch_types": [],
    }
    models = [FixtureModel({"judge": response}, model_id=name) for name in ("m1", "m2")]
    report = await run_bakeoff([pair], models, dataset_version="synthetic-test-only")
    assert report["prompt_version"] == "v2"
    for model in report["models"].values():
        assert model["metrics"]["invalid_json_rate"] == 0
        assert model["metrics"]["quote_verification_failure_rate"] == 0
