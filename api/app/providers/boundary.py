"""Explicit conversions between extraction details and A1's frozen public schema."""

from urllib.parse import quote

import httpx

from api.app.ingest.models import ParsedReference
from api.app.providers.metadata import normalize_doi
from api.app.providers.models import Work
from contracts.schema import Reference


def parsed_reference(reference: Reference) -> ParsedReference:
    # A1 deliberately has no venue, PMID or work-type fields. Do not infer index
    # coverage from a DOI alone: books/software can have DOIs too.
    return ParsedReference(
        id=reference.id,
        raw=reference.raw_text,
        title=reference.title,
        authors=reference.authors,
        year=reference.year,
        doi=normalize_doi(reference.doi) or reference.doi,
        arxiv=reference.arxiv_id,
        kind="preprint" if reference.arxiv_id else "unknown",
    )


def public_reference(reference: ParsedReference) -> Reference:
    return Reference(
        id=reference.id,
        raw_text=reference.raw,
        title=reference.title,
        authors=reference.authors,
        year=reference.year,
        doi=reference.doi,
        arxiv_id=reference.arxiv,
    )


def work_reference(work: Work, reference_id: str) -> Reference:
    url = None
    if work.oa_url:
        try:
            parsed = httpx.URL(work.oa_url)
            if parsed.scheme == "https" and parsed.host and not parsed.userinfo:
                url = str(parsed)
        except httpx.InvalidURL:
            pass
    return Reference(
        id=reference_id,
        raw_text=work.title or work.id,
        title=work.title,
        authors=work.authors,
        year=work.year,
        doi=work.doi,
        arxiv_id=work.arxiv,
        url=url,
    )


def reference_work(reference: Reference) -> Work:
    return Work(
        provider="contract",
        id=reference.doi or reference.arxiv_id or reference.id,
        title=reference.title,
        authors=reference.authors,
        year=reference.year,
        doi=normalize_doi(reference.doi),
        arxiv=reference.arxiv_id,
        oa_url=reference.url,
    )


def receipt_urls(work: Work) -> list[str]:
    urls = []
    if work.doi:
        urls.append("https://doi.org/" + quote(work.doi, safe="/"))
    if work.provider == "openalex":
        urls.append("https://openalex.org/" + quote(work.id.rsplit("/", 1)[-1], safe=""))
    if work.arxiv:
        urls.append("https://arxiv.org/abs/" + quote(work.arxiv, safe="/"))
    return urls
