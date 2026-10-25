"""Unlabeled review candidates; never silently promote these to bakeoff ground truth.

Validation is offline. --fetch explicitly downloads anonymous public evidence through
Gateway, without Settings, environment credentials, authenticated APIs or model calls.
"""

import argparse
import asyncio
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

import pdfplumber
from pdfminer.pdfexceptions import PDFException, PSException
from pdfplumber.utils.exceptions import PdfminerException
from pydantic import Field, ValidationError

from api.app.eval.bakeoff import Label
from api.app.ingest.models import Record
from api.app.providers.http import Gateway
from api.app.verify.gates import quote_matches

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
PAPERS = ("paper1_attention", "paper2_retracted_reference", "paper3_planted_problems")


class EvidenceSource(Record):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://")
    retrieved_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cache_key: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    coverage: Literal["ABSTRACT_ONLY", "FULL_TEXT"]
    format: Literal["html", "xml", "pdf", "fixture_pdf"]
    caution: str | None = None


class Candidate(Record):
    id: str = Field(min_length=1)
    paper_id: Literal["paper1_attention", "paper2_retracted_reference", "paper3_planted_problems"]
    paper_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    synthetic: bool
    page: int = Field(ge=1)
    citing_sentence: str = Field(min_length=1)
    citation_marker: str = Field(min_length=1)
    cited_reference: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    quote_role: Literal["supporting_context", "limiting_context", "method_context"]
    human_label: Label | None = None
    labeled_by: str | None = None


class Proposal(Record):
    candidate_id: str
    proposed_label: Label
    reason: str = Field(min_length=1)
    author: Literal["Codex proposal; not a human annotation"]


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def canonical_source(identifier: str) -> str:
    value = identifier.strip().casefold()
    value = re.sub(r"^https://(?:dx\.)?doi.org/", "doi:", value)
    value = re.sub(r"^https://arxiv.org/(?:abs|pdf)/", "arxiv:", value)
    return re.sub(r"v\d+$", "", value.removesuffix(".pdf")) if value.startswith("arxiv:") else value


def pair_key(candidate: Candidate) -> tuple[str, str, str]:
    return (
        candidate.paper_sha256,
        normalized(candidate.citing_sentence).casefold(),
        canonical_source(candidate.source_id),
    )


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible_text(content: bytes) -> str:
    parser = VisibleHTML()
    parser.feed(content.decode("utf-8", errors="replace"))
    return normalized(" ".join(parser.parts))


def pdf_texts(path: Path) -> list[str]:
    """Keep page and column boundaries; retain printed hyphens and scientific symbols."""
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                texts.append(normalized(page.extract_text(x_tolerance=1) or ""))
                for bounds in (
                    (0, 0, page.width / 2, page.height),
                    (page.width / 2, 0, page.width, page.height),
                ):
                    texts.append(normalized(page.crop(bounds).extract_text(x_tolerance=1) or ""))
    except (OSError, ValueError, PDFException, PSException, PdfminerException):
        return []
    return texts


def read_jsonl(path: Path, model: type[Record]) -> list:
    return [
        model.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]


def validate_candidates(
    candidates: list[Candidate],
    sources: list[EvidenceSource],
    proposals: list[Proposal],
    *,
    root: Path = ROOT,
    check_evidence: bool = True,
    expected_count: int = 40,
) -> list[str]:
    errors: list[str] = []
    ids, pairs, source_ids = set(), set(), set()
    lookup = {}
    source_texts = {}
    paper_pages = {}
    if len(candidates) != expected_count:
        errors.append(f"expected {expected_count} candidates, found {len(candidates)}")
    if {c.paper_id for c in candidates} != set(PAPERS):
        errors.append("candidates must cover all three fixture papers")
    for source in sources:
        key = canonical_source(source.id)
        if key in source_ids:
            errors.append(f"duplicate source identifier: {source.id}")
        source_ids.add(key)
        lookup[key] = source
        if check_evidence:
            path = (
                root / "fixtures/pdfs" / f"{source.cache_key}.pdf"
                if source.format == "fixture_pdf"
                else root / "data/evaluation_sources" / f"{source.cache_key}.{source.format}"
            )
            if not path.is_file():
                errors.append(f"missing evidence: {source.id}; use --fetch for public artifacts")
                continue
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != source.sha256:
                errors.append(f"evidence hash changed: {source.id}; review before updating receipt")
                continue
            if source.format in {"fixture_pdf", "pdf"}:
                source_texts[key] = pdf_texts(path)
                if not source_texts[key]:
                    errors.append(f"unreadable source PDF: {source.id}")
            else:
                source_texts[key] = [visible_text(raw)]
    for c in candidates:
        if c.id in ids:
            errors.append(f"duplicate candidate ID: {c.id}")
        ids.add(c.id)
        if pair_key(c) in pairs:
            errors.append(f"duplicate claim-source pair: {c.id}")
        pairs.add(pair_key(c))
        if c.synthetic != (c.paper_id != "paper1_attention"):
            errors.append(f"incorrect synthetic marking: {c.id}")
        if c.human_label is not None or c.labeled_by is not None:
            errors.append(f"human review fields must remain empty in candidate staging: {c.id}")
        if c.citation_marker not in c.citing_sentence:
            errors.append(f"citation marker missing from sentence: {c.id}")
        key = canonical_source(c.source_id)
        if key not in lookup:
            errors.append(f"missing source receipt: {c.id}")
        if len(c.source_quote.split()) < 4:
            errors.append(f"quote too short: {c.id}")
        if not check_evidence:
            continue
        if c.paper_id not in paper_pages:
            path = root / "fixtures/pdfs" / f"{c.paper_id}.pdf"
            if not path.is_file():
                errors.append(f"missing citing PDF: {c.paper_id}")
                paper_pages[c.paper_id] = ("", [])
            else:
                pages = pdf_texts(path)[::3]
                paper_pages[c.paper_id] = (hashlib.sha256(path.read_bytes()).hexdigest(), pages)
        digest, pages = paper_pages[c.paper_id]
        if digest != c.paper_sha256:
            errors.append(f"citing PDF hash changed: {c.id}")
        if c.page > len(pages) or normalized(c.citing_sentence) not in pages[c.page - 1]:
            errors.append(f"citing sentence not on recorded PDF page: {c.id}")
        if normalized(c.cited_reference) not in " ".join(pages):
            errors.append(f"cited reference not in recorded PDF: {c.id}")
        texts = source_texts.get(key, [])
        if key in lookup and lookup[key].format in {"pdf", "fixture_pdf"}:
            match = re.match(r"PDF page (\d+),", c.source_locator)
            if match:
                index = (int(match[1]) - 1) * 3
                texts = texts[index : index + 3] if index >= 0 else []
            else:
                texts = []
        if not any(
            normalized(c.source_quote) in text and quote_matches(c.source_quote, text)
            for text in texts
        ):
            errors.append(f"missing or inexact source quote: {c.id}")
    proposal_ids = [p.candidate_id for p in proposals]
    if set(proposal_ids) != ids or len(proposal_ids) != len(ids):
        errors.append("proposals must cover each candidate exactly once")
    return errors


async def fetch_evidence(sources: list[EvidenceSource], root: Path = ROOT) -> list[str]:
    errors = []
    cache = root / "data/evaluation_sources"
    cache.mkdir(parents=True, exist_ok=True)
    async with Gateway() as gateway:
        for source in sources:
            if source.format == "fixture_pdf":
                continue
            path = cache / f"{source.cache_key}.{source.format}"
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == source.sha256:
                continue
            result = await gateway.safe_fetch(source.url)
            if result.error or result.status != 200:
                errors.append(f"fetch failed: {source.id}: {result.error or result.status}")
                continue
            if hashlib.sha256(result.content).hexdigest() != source.sha256:
                errors.append(
                    f"remote content changed: {source.id}; pinned receipt not overwritten"
                )
                continue
            path.write_bytes(result.content)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="fetch anonymous public evidence")
    parser.add_argument(
        "--structure-only", action="store_true", help="does not verify source quotes"
    )
    args = parser.parse_args()
    try:
        candidates = read_jsonl(HERE / "candidates.jsonl", Candidate)
        sources = read_jsonl(HERE / "sources.jsonl", EvidenceSource)
        proposals = read_jsonl(HERE / "proposed_labels.jsonl", Proposal)
        errors = asyncio.run(fetch_evidence(sources)) if args.fetch else []
        errors += validate_candidates(
            candidates, sources, proposals, check_evidence=not args.structure_only
        )
    except (OSError, ValueError, ValidationError) as error:
        errors = [str(error)]
    print(
        json.dumps(
            {"valid": not errors, "evidence_checked": not args.structure_only, "errors": errors},
            indent=2,
        )
    )
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
