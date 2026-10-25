"""Prepare pinned, limited evidence offline; artifact availability is not text coverage."""

import hashlib
import io
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from xml.etree.ElementTree import ParseError

import pdfplumber
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from api.app.eval.candidates import ROOT, EvidenceSource, canonical_source, normalized
from api.app.ingest.pdf import PDF_ERRORS
from api.app.sources.acquire import Source


@dataclass(frozen=True)
class PDFAbstractRegion:
    artifact_sha256: str
    bounds: tuple[float, float, float, float]
    text_sha256: str
    description: str


# First-page glyph bounds were inspected against each pinned artifact. Text hashes
# additionally reject extraction drift, partial words or accidental column mixing.
# These regions contain only the abstract/standfirst, never whole-source coverage.
PDF_ABSTRACTS = {
    "arxiv:1703.03906": PDFAbstractRegion(
        "6ae9257b347f5982f29618fcd774a03b5eb8795881c017f889e90f7956bcb22a",
        (70, 235, 293, 577),
        "3a2b2456d8a2ce798d274e4ef3bb59594591df2a8dc357c9378053e97e6cbf1b",
        "first-page left-column abstract",
    ),
    "arxiv:1512.00567": PDFAbstractRegion(
        "80e30acdfa89bcb41a00c8b221cb9a1dc44256897e75af8762f171ec9dc77b85",
        (48, 283, 291, 555),
        "60d652e1f244da70889aa0011435093083a009d34d9d7ccf076d65440bb191df",
        "first-page left-column abstract",
    ),
    "doi:10.1038/nature14539": PDFAbstractRegion(
        "18b910be375cd8c9358eb8868a65ff4c9cdcea643d62cefdc3d202c133ca5fc2",
        (44, 181, 553, 258),
        "636912b64f4fabf88fb665f794a74c3cc973a4cd6efb0bbaa75f32e83219f264",
        "first-page publisher opening summary (standfirst)",
    ),
    "arxiv:1706.03762": PDFAbstractRegion(
        "bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697",
        (140, 410, 473, 580),
        "87023b55729583bcdf2d13ec8e2d4ab5002ef380a819c58ac34f2d5b0c247a37",
        "first-page centered abstract",
    ),
}


class AbstractHTML(HTMLParser):
    """Select an actual abstract, excluding page chrome and hidden script content."""

    VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    HIDDEN = {"script", "style", "template", "noscript"}

    def __init__(self, selector: str):
        super().__init__(convert_charrefs=True)
        self.selector = selector
        self.metadata: dict[str, list[str]] = {}
        self.stack: list[str] = []
        self.depth: int | None = 0 if selector == "fragment" else None
        self.parts: list[str] = []
        self.abstracts: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("name") and values.get("content"):
            self.metadata.setdefault(values["name"], []).append(values["content"])
        if tag not in self.VOID:
            self.stack.append(tag)
        expected = "blockquote" if self.selector == "arxiv" else "p"
        if self.depth is None and tag == expected and "abstract" in values.get("class", "").split():
            self.depth = len(self.stack)
            self.parts = []
        if self.depth is not None and not any(t in self.HIDDEN for t in self.stack):
            if tag in {"p", "br", "h4", "div", "li"}:
                self.parts.append(" ")
            elif tag in {"sup", "sub"}:
                self.parts.append("^{" if tag == "sup" else "_{")

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        if self.depth is not None and not any(t in self.HIDDEN for t in self.stack):
            if tag in {"sup", "sub"}:
                self.parts.append("}")
            elif tag in {"p", "h4", "div", "li"}:
                self.parts.append(" ")
        if self.depth is not None and self.depth > 0 and index + 1 == self.depth:
            self.abstracts.append(normalized("".join(self.parts)))
            self.depth = None
        del self.stack[index:]

    def handle_data(self, data):
        if self.depth is not None and not any(t in self.HIDDEN for t in self.stack):
            self.parts.append(data)


def html_abstract(raw: bytes, source: EvidenceSource) -> str | None:
    key = canonical_source(source.id)
    selector = "arxiv" if key.startswith("arxiv:") else "jmlr"
    if selector == "jmlr" and not key.startswith("jmlr:"):
        return None
    parser = AbstractHTML(selector)
    parser.feed(raw.decode("utf-8", errors="strict"))
    titles = parser.metadata.get("citation_title", [])
    if len(titles) != 1 or normalized(titles[0]).casefold() != normalized(source.title).casefold():
        return None
    if selector == "arxiv":
        identifiers = parser.metadata.get("citation_arxiv_id", [])
        if len(identifiers) != 1 or canonical_source("arxiv:" + identifiers[0]) != key:
            return None
    else:
        urls = parser.metadata.get("citation_public_url", [])
        if len(urls) != 1:
            return None
        url = urlparse(urls[0])
        identifier = "jmlr:" + url.path.removeprefix("/papers/").removesuffix(".html")
        if url.hostname not in {"jmlr.org", "www.jmlr.org"} or identifier != key:
            return None
    if len(parser.abstracts) != 1:
        return None
    return re.sub(r"^Abstract:\s*", "", parser.abstracts[0]).strip() or None


def xml_abstract(raw: bytes, source: EvidenceSource) -> str | None:
    root = ElementTree.fromstring(raw, forbid_dtd=True)
    results = root.findall(".//result")
    if len(results) != 1:
        return None
    result = results[0]
    doi = result.findtext("doi", "")
    title = result.findtext("title", "")
    if (
        canonical_source("doi:" + doi) != canonical_source(source.id)
        or normalized(title).casefold() != normalized(source.title).casefold()
    ):
        return None
    abstract = result.find("abstractText")
    if abstract is None:
        return None
    # EuropePMC may encode headings as escaped HTML inside abstractText. Parse
    # only that subtree, never the rest of the search response or its metadata.
    text = (abstract.text or "") + "".join(
        ElementTree.tostring(child, encoding="unicode") for child in abstract
    )
    parser = AbstractHTML("fragment")
    parser.feed(text)
    return normalized("".join(parser.parts)) or None


def pdf_abstract(raw: bytes, source: EvidenceSource) -> str | None:
    region = PDF_ABSTRACTS.get(canonical_source(source.id))
    if region is None or region.artifact_sha256 != source.sha256:
        return None
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        if not pdf.pages:
            return None
        text = normalized(pdf.pages[0].crop(region.bounds).extract_text(x_tolerance=1) or "")
    if hashlib.sha256(text.encode()).hexdigest() != region.text_sha256:
        return None
    return text or None


def prepare_evidence(source: EvidenceSource, root: Path = ROOT) -> Source:
    """Return an authentic scoped abstract or NONE; never promote a receipt to FULL_TEXT."""
    result = Source(
        work_id=canonical_source(source.id),
        evidence_level="NONE",
        origin=source.url,
        reason="pinned evidence artifact is missing",
    )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", source.cache_key):
        result.reason = "unsafe evidence cache key"
        return result
    directory = root / (
        "fixtures/pdfs" if source.format == "fixture_pdf" else "data/evaluation_sources"
    )
    suffix = "pdf" if source.format == "fixture_pdf" else source.format
    path = directory / f"{source.cache_key}.{suffix}"
    try:
        if not directory.resolve().is_relative_to(
            root.resolve()
        ) or not path.resolve().is_relative_to(directory.resolve()):
            result.reason = "evidence path escapes its cache directory"
            return result
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source.sha256:
            result.reason = "pinned evidence artifact hash mismatch"
            return result
        if source.format == "html":
            text = html_abstract(raw, source)
            scope = "identity-checked HTML abstract element"
        elif source.format == "xml":
            text = xml_abstract(raw, source)
            scope = "identity-checked EuropePMC abstractText"
        else:
            text = pdf_abstract(raw, source)
            region = PDF_ABSTRACTS.get(canonical_source(source.id))
            scope = f"audited PDF {region.description}" if region else "PDF abstract"
        if not text:
            result.reason = "authentic abstract identity or extraction scope could not be verified"
            return result
        result.evidence_level = "ABSTRACT"
        result.text = result.abstract = text
        result.abstract_origin = source.url
        result.reason = f"{scope}; abstract-only coverage, not whole-source verification"
        return result
    except (OSError, RuntimeError, UnicodeError, ParseError, DefusedXmlException, *PDF_ERRORS):
        result.reason = "pinned evidence artifact is missing, unreadable or unsafe to parse"
        return result
