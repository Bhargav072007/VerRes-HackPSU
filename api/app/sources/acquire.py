import asyncio
import html
import io
import json
import re
from typing import Literal
from urllib.parse import quote
from xml.etree.ElementTree import ParseError

import pdfplumber
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from api.app.ingest.models import ParsedReference, Record
from api.app.ingest.pdf import PDF_ERRORS, valid_pdf
from api.app.providers.http import MAX_BYTES, Gateway
from api.app.providers.metadata import normalize_doi
from api.app.providers.models import Work
from api.app.resolve.existence import agrees, metadata_mismatch, normalize, title_similarity

PARTIAL_PDF_PREFIX = "Partial PDF text coverage: "
PARTIAL_PDF_SECTION = "Extracted text (partial coverage)"


class Source(Record):
    work_id: str
    whole_source: bool = True
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


def extract_pdf_text(data: bytes, work: Work) -> Source | None:
    if not valid_pdf(data) or len(data) > MAX_BYTES:
        return None
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if not pdf.pages or len(pdf.pages) > 2000:
                return None
            # Figures do not invalidate extracted prose, but they prevent whole-source
            # absence claims. A page containing only a running header is not usable text.
            graphical = any(page.images or page.curves or page.rects for page in pdf.pages)
            pages = [page.extract_text() or "" for page in pdf.pages]
            # Blank/scanned pages mean text coverage cannot justify whole-source negatives.
            word_counts = [len(re.findall(r"\w+", page)) for page in pages]
            if not any(count >= 12 for count in word_counts):
                return None
            partial = graphical or any(count < 8 for count in word_counts)
            value = "\n\n".join(pages)
            if len(value) > 2_000_000:
                return None
            if not work.title or title_similarity(work.title, value[:700]) < 0.9:
                return None
            if not work.authors or not re.search(
                rf"\b{re.escape(normalize(work.authors[0]))}\b", normalize(value[:2000])
            ):
                return None
            return Source(
                work_id=work.id,
                evidence_level="FULL_TEXT",
                text=value,
                whole_source=not partial,
                reason=(
                    PARTIAL_PDF_PREFIX + "some pages or graphical content may be missing; "
                    "absence cannot be established."
                )
                if partial
                else "metadata-selected PDF; title and first author matched",
            )
    except PDF_ERRORS:
        return None


def extract_full_pdf(data: bytes, work: Work) -> str | None:
    """Compatibility helper for callers that require complete text coverage."""
    extracted = extract_pdf_text(data, work)
    return extracted.text if extracted and extracted.whole_source else None


async def pubmed_abstract(doi: str, gateway: Gateway) -> str | None:
    """Abstract from PubMed by DOI; publishers like Elsevier withhold abstracts elsewhere."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    found = await gateway.safe_fetch(
        f"{base}esearch.fcgi?db=pubmed&retmode=json&term={quote(doi, safe='')}%5Bdoi%5D"
    )
    if found.error or found.status != 200:
        return None
    try:
        ids = json.loads(found.content)["esearchresult"]["idlist"]
    except (ValueError, KeyError, TypeError):
        return None
    if len(ids) != 1:
        return None
    record = await gateway.safe_fetch(f"{base}efetch.fcgi?db=pubmed&retmode=xml&id={ids[0]}")
    if record.error or record.status != 200:
        return None
    xml = record.content.decode("utf-8", "replace")
    parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", xml, re.S)
    text = " ".join(re.sub(r"<[^>]+>", "", part).strip() for part in parts).strip()
    return html.unescape(text) or None


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
            extracted = await asyncio.to_thread(extract_pdf_text, response.content, work)
            if extracted:
                return extracted.model_copy(
                    update={
                        "abstract": abstract,
                        "abstract_origin": abstract_origin,
                        "origin": url,
                    }
                )
            reasons.append("PDF text coverage or identity could not be verified")
        else:
            reasons.append(response.error or f"HTTP {response.status}")
    if not abstract and work.doi:
        abstract = await pubmed_abstract(work.doi, gateway)
        if abstract:
            abstract_origin = "pubmed"
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
