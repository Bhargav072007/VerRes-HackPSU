import json

import httpx
from app.ingest.tei import parse_tei
from app.providers.http import Gateway
from app.providers.metadata import Crossref, OpenAlex
from app.sources.acquire import acquire_source
from app.verify.pipeline import verify_citation
from conftest import FixtureModel, judgment


async def test_offline_tei_to_verified_receipt(tei, pdf_bytes, claim):
    """Real module composition; only HTTP and model boundaries are fixture-backed."""
    from app.resolve.existence import resolve_reference

    paper = parse_tei(tei).paper
    crossref = {
        "message": {
            "DOI": "10.1234/animal.1",
            "title": ["Controlled animal intervention study"],
            "author": [{"family": "Smith"}],
            "published": {"date-parts": [[2024]]},
            "abstract": "<p>The treatment reduced inflammation in mice by 20 percent.</p>",
        }
    }
    openalex = {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.1234/animal.1",
        "title": "Controlled animal intervention study",
        "publication_year": 2024,
        "authorships": [{"author": {"display_name": "Jane Smith"}}],
        "best_oa_location": {"pdf_url": "https://papers.example/source.pdf"},
        "meta": {"cost_usd": 0},
    }

    def handler(request):
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=crossref)
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json=openalex)
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "papers.example"
        return httpx.Response(200, content=pdf_bytes())

    async def dns(host, port):
        return ["93.184.216.34"]

    async with Gateway(resolver=dns, transport=httpx.MockTransport(handler)) as gateway:
        resolved = await resolve_reference(
            paper.references[0], Crossref(gateway, "r@example.org"), OpenAlex(gateway)
        )
        assert resolved.status == "FOUND" and resolved.work.oa_url
        source = await acquire_source(resolved.work, gateway)
    assert source.evidence_level == "FULL_TEXT"
    assert source.abstract_origin == "crossref"
    # This fixture's citing sentence has no number; the split must not introduce one.
    claim.magnitude = None
    model = FixtureModel(
        {
            "classify": {"items": [{"citation_id": "c00001", "function": "SPECIFIC_CLAIM"}]},
            "split": {"ambiguous": False, "claims": [claim.model_dump()]},
            "judge": judgment().model_dump(),
        }
    )
    verified = await verify_citation(paper.citations[0], source, model)
    assert verified.finding.status == "SUPPORTED"
    quote = verified.finding.evidence[0]
    passage = next(p for p in verified.finding.passages if p.id == quote.passage_id)
    assert quote.quote in passage.text and passage.text in source.text
    assert verified.finding.source_origin == "https://papers.example/source.pdf"
    assert json.loads(verified.model_dump_json())["finding"]["model_ids"] == [model.model_id]
