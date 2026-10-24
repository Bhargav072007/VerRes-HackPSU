import asyncio
import io
import re
from typing import Literal
from xml.etree.ElementTree import ParseError

import pdfplumber
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from api.app.ingest.models import ParsedReference, Record
from api.app.ingest.pdf import PDF_ERRORS, valid_pdf
from api.app.providers.http import Gateway
from api.app.providers.metadata import normalize_doi
from api.app.providers.models import Work
from api.app.resolve.existence import agrees, metadata_mismatch, normalize, title_similarity


class Source(Record):
    work_id: str
    evidence_level: Literal["FULL_TEXT", "ABSTRACT", "NONE"]
    text: str = ""
    abstract: str | None = None
    abstract_origin: str | None = None
    origin: str | None = None
    reason: str


def abstract_text(work: Work) -> str | None:
    if work.abstract:
        try:
            root = ElementTree.fromstring("<root>" + work.abstract + "</root>", forbid_dtd=True)
            value = " ".join("".join(root.itertext()).split())
            if value:
                return value
        except (ParseError, DefusedXmlException, ValueError):
            # Plain abstracts need no XML interpretation; malformed JATS is not guessed at.
            if "<" not in work.abstract and ">" not in work.abstract:
                return work.abstract.strip() or None
    index = work.abstract_inverted_index
    if not index:
        return None
    tokens = {}
    for word, positions in index.items():
        for position in positions:
            if position < 0 or position > 100_000 or position in tokens:
                return None
            tokens[position] = word
    if not tokens or set(tokens) != set(range(len(tokens))):
        return None
    return " ".join(tokens[i] for i in range(len(tokens)))


def extract_full_pdf(data: bytes, work: Work) -> str | None:
    if not valid_pdf(data):
        return None
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if not pdf.pages or len(pdf.pages) > 2000:
                return None
            pages = [page.extract_text() or "" for page in pdf.pages]
            # Blank/scanned pages mean text coverage cannot justify whole-source negatives.
            if any(not page.strip() for page in pages):
                return None
            value = "\n\n".join(pages)
            if len(value) > 2_000_000:
                return None
            if not work.title or title_similarity(work.title, value[:700]) < 0.9:
                return None
            if not work.authors or not re.search(
                rf"\b{re.escape(normalize(work.authors[0]))}\b", normalize(value[:2000])
            ):
                return None
            return value
    except PDF_ERRORS:
        return None


async def acquire_source(
    work: Work, gateway: Gateway, *, crossref_work: Work | None = None
) -> Source:
    if crossref_work:
        ref = ParsedReference(
            id=work.id, raw="", title=work.title, authors=work.authors, year=work.year
        )
        same_doi = normalize_doi(work.doi) is not None and normalize_doi(work.doi) == normalize_doi(
            crossref_work.doi
        )
        if metadata_mismatch(ref, crossref_work) or not (same_doi or agrees(ref, crossref_work)):
            crossref_work = None
    abstract = abstract_text(crossref_work) if crossref_work else None
    abstract_origin = crossref_work.provider if abstract and crossref_work else work.abstract_origin
    abstract = abstract or abstract_text(work)
    urls = []
    if work.oa_url:
        urls.append(work.oa_url)
    if work.arxiv and re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", work.arxiv, re.I):
        urls.append(f"https://arxiv.org/pdf/{work.arxiv}")
    reasons = []
    for url in dict.fromkeys(urls):
        response = await gateway.safe_fetch(url)
        if not response.error and response.status == 200:
            value = await asyncio.to_thread(extract_full_pdf, response.content, work)
            if value:
                return Source(
                    work_id=work.id,
                    evidence_level="FULL_TEXT",
                    text=value,
                    abstract=abstract,
                    abstract_origin=abstract_origin,
                    origin=url,
                    reason="metadata-selected PDF; title and first author matched",
                )
            reasons.append("PDF text coverage or identity could not be verified")
        else:
            reasons.append(response.error or f"HTTP {response.status}")
    if abstract:
        return Source(
            work_id=work.id,
            evidence_level="ABSTRACT",
            text=abstract,
            abstract=abstract,
            origin=abstract_origin or work.provider,
            abstract_origin=abstract_origin or work.provider,
            reason="abstract only; full source unavailable",
        )
    return Source(
        work_id=work.id,
        evidence_level="NONE",
        origin=work.provider,
        reason="; ".join(reasons) or "no accessible source text or abstract",
    )
