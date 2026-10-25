"""Explicit conversions between extraction details and A1's frozen public schema."""

import re
from urllib.parse import quote

import httpx

from api.app.ingest.models import ParsedReference
from api.app.providers.identifiers import extract_arxiv, normalize_arxiv
from api.app.providers.metadata import normalize_doi
from api.app.providers.models import Work
from contracts.schema import Reference


def parsed_reference(reference: Reference) -> ParsedReference:
    arxiv = normalize_arxiv(reference.arxiv_id) or extract_arxiv(reference.raw_text)
    kind = "preprint" if arxiv else reference_kind(reference)
    raw = re.sub(r"(?<=\w)-\s+(?=\w)", "", reference.raw_text)
    parts = re.split(re.escape(reference.title), raw, flags=re.I) if reference.title else []
    venue = parts[-1].strip(" .,") if len(parts) > 1 else None
    return ParsedReference(
        id=reference.id,
        raw=reference.raw_text,
        title=reference.title,
        authors=reference.authors,
        year=reference.year,
        venue=venue,
        doi=normalize_doi(reference.doi) or reference.doi,
        arxiv=arxiv or reference.arxiv_id,
        kind=kind,
    )


def reference_kind(reference: Reference) -> str:
    """Infer journal coverage only from explicit venue + volume/issue/page syntax."""
    if not reference.title or not reference.authors or not reference.year:
        return "unknown"
    parts = re.split(re.escape(reference.title), reference.raw_text, flags=re.I)
    tail = parts[-1] if len(parts) > 1 else ""
    if re.search(r"\b(?:ISBN|Press|publisher|chapter)\b", tail, re.I):
        return "book"
    if re.search(r"https?://(?!doi\.org)|\b(?:accessed|retrieved)\b", tail, re.I):
        return "website"
    if re.search(r"[A-Za-z][^.;]*[,;]\s*\d+\s*\(\d+\)\s*[:,]\s*\d+\s*[-–]\s*\d+", tail):
        return "journal-article"
    return "unknown"


def public_reference(reference: ParsedReference) -> Reference:
    return Reference(
        id=reference.id,
        raw_text=reference.raw,
        title=reference.title,
        authors=reference.authors,
        year=reference.year,
        doi=reference.doi,
        arxiv_id=normalize_arxiv(reference.arxiv),
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
