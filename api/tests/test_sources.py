import httpx
from app.providers.http import Gateway
from app.providers.models import Work
from app.sources.acquire import abstract_text, acquire_source, extract_full_pdf


def test_abstract_jats_and_inverted_index():
    work = Work(
        provider="crossref",
        id="a",
        abstract="<jats:p xmlns:jats='x'>A <jats:italic>real</jats:italic> abstract.</jats:p>",
    )
    assert abstract_text(work) == "A real abstract."
    work.abstract = None
    work.abstract_inverted_index = {"A": [0], "real": [1], "abstract.": [2]}
    assert abstract_text(work) == "A real abstract."
    work.abstract_inverted_index = {"bad": [0, 0]}
    assert abstract_text(work) is None


def test_source_identity_and_text_coverage(pdf_bytes):
    work = Work(
        provider="openalex", id="a", title="Controlled animal intervention study", authors=["Smith"]
    )
    assert "inflammation" in extract_full_pdf(pdf_bytes(), work)
    assert (
        extract_full_pdf(pdf_bytes(title="Entirely unrelated document", author="Jones"), work)
        is None
    )


async def test_pdf_then_abstract_fallback():
    async def dns(host, port):
        return ["93.184.216.34"]

    work = Work(
        provider="openalex",
        id="a",
        oa_url="https://example.org/paper",
        abstract_inverted_index={"An": [0], "abstract": [1]},
    )
    async with Gateway(
        resolver=dns, attempts=1, transport=httpx.MockTransport(lambda r: httpx.Response(404))
    ) as gateway:
        source = await acquire_source(work, gateway)
    assert source.evidence_level == "ABSTRACT" and source.text == "An abstract"


async def test_no_source_preserves_uncertainty():
    async with Gateway() as gateway:
        source = await acquire_source(Work(provider="crossref", id="a"), gateway)
    assert source.evidence_level == "NONE" and source.reason
