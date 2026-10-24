"""Conservative numbered-reference fallback. Output always remains basic/NEEDS_REVIEW."""

import re
import threading

import pypdfium2

from api.app.ingest.models import (
    ParsedCitation,
    ParsedPaper,
    ParsedReference,
    ParsedSentence,
    ParseResult,
)
from api.app.ingest.tei import identifiers

PDF_LIMIT = 25 * 1024 * 1024
PAGE_LIMIT = 80
ENTRY = re.compile(r"(?m)^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.)])\s+")
MARKER = re.compile(r"\[(\d{1,4}(?:\s*[-,]\s*\d{1,4})*)\]")
# PDFium's native API is not thread-safe; concurrent jobs use one native parser at a time.
PDFIUM_LOCK = threading.Lock()


def marker_numbers(value: str) -> list[int]:
    if not re.fullmatch(r"\d{1,4}(?:\s*[-,]\s*\d{1,4})*", value):
        return []
    numbers = []
    for part in value.split(","):
        bounds = [int(n.strip()) for n in part.split("-")]
        if len(bounds) == 1:
            numbers.append(bounds[0])
        elif bounds[0] <= bounds[1] <= bounds[0] + 20:
            numbers.extend(range(bounds[0], bounds[1] + 1))
    return list(dict.fromkeys(numbers))


def parse_basic_pages(pages: list[str]) -> ParsedPaper:
    paper = ParsedPaper()
    body, bibliography = [], []
    in_references = False
    section = "Body"
    for page in pages:
        for line in page.splitlines():
            line = line.strip()
            if re.fullmatch(r"references|bibliography", line, re.I):
                in_references = True
            elif in_references:
                bibliography.append(line)
            elif re.fullmatch(
                r"abstract|introduction|methods|results|discussion|conclusions?", line, re.I
            ):
                section = line.title()
            elif line:
                body.append((section, line))
    raw = "\n".join(bibliography)
    matches = list(ENTRY.finditer(raw))
    entries = {}
    for i, match in enumerate(matches):
        number = int(match.group(1) or match.group(2))
        value = " ".join(
            raw[match.end() : matches[i + 1].start() if i + 1 < len(matches) else None].split()
        )
        # Duplicate numbers are ambiguous; never attach a sentence to either guess.
        entries[number] = None if number in entries else value
    for number, value in entries.items():
        if not value:
            continue
        year = re.search(r"\b(?:18|19|20)\d{2}\b", value)
        paper.references.append(
            ParsedReference(
                id=f"b{number}",
                raw=value,
                year=int(year.group()) if year else None,
                **identifiers(value),
            )
        )
    # Join wrapped lines before sentence splitting; preserve section changes.
    blocks = []
    for section, line in body:
        if blocks and blocks[-1][0] == section:
            blocks[-1] = (section, blocks[-1][1] + " " + line)
        else:
            blocks.append((section, line))
    for section, block in blocks:
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", block):
            paper.sentences.append(
                ParsedSentence(
                    id=f"s{len(paper.sentences) + 1:05d}",
                    text=sentence,
                    section=section,
                )
            )
    references = {r.id: r for r in paper.references}
    for index, sentence in enumerate(paper.sentences):
        for marker in MARKER.finditer(sentence.text):
            for number in marker_numbers(marker.group(1)):
                reference = references.get(f"b{number}")
                if reference is None:
                    continue
                paper.citations.append(
                    ParsedCitation(
                        id=f"c{len(paper.citations) + 1:05d}",
                        reference_id=reference.id,
                        sentence_id=sentence.id,
                        text=sentence.text,
                        marker=marker.group(),
                        section=sentence.section,
                        reference_raw=reference.raw,
                        previous=paper.sentences[index - 1].text if index else None,
                        next=paper.sentences[index + 1].text
                        if index + 1 < len(paper.sentences)
                        else None,
                    )
                )
    return paper


def fallback_pdf(data: bytes) -> ParseResult:
    reason = "basic parser (pypdfium2 + regex); metadata and citation links may be incomplete"
    if not data.startswith(b"%PDF-") or len(data) > PDF_LIMIT:
        return ParseResult(
            status="FAILED", parser="pypdfium2", reasons=["invalid or oversized PDF"]
        )
    try:
        with PDFIUM_LOCK, pypdfium2.PdfDocument(data) as document:
            if not 0 < len(document) <= PAGE_LIMIT:
                return ParseResult(
                    status="FAILED", parser="pypdfium2", reasons=["PDF must have 1–80 pages"]
                )
            pages = []
            for index in range(len(document)):
                page, text = document[index], None
                try:
                    text = page.get_textpage()
                    pages.append(text.get_text_range())
                finally:
                    if text is not None:
                        text.close()
                    page.close()
        paper = parse_basic_pages(pages)
        return ParseResult(
            status="PARTIAL" if paper.sentences else "FAILED",
            parser="pypdfium2",
            paper=paper,
            reasons=[reason],
        )
    except (pypdfium2.PdfiumError, ValueError, TypeError, OverflowError):
        return ParseResult(status="FAILED", parser="pypdfium2", reasons=["PDF extraction failed"])
