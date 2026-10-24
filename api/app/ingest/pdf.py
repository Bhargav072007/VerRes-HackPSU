import asyncio
import io
import re

import pdfplumber
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams
from pdfminer.pdfexceptions import PDFException
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.psparser import PSEOF
from pdfplumber.utils.exceptions import PdfminerException

from api.app.ingest.models import HiddenScan, HiddenSpan, ParsedPaper, ParsedSentence, ParseResult
from api.app.ingest.tei import parse_tei
from api.app.providers.http import MAX_BYTES, Gateway

INSTRUCTIONS = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|"
    r"system\s+prompt|you\s+are\s+(?:chatgpt|an?\s+assistant)|"
    r"(?:return|output|mark)\s+(?:only\s+)?(?:supported|approved|positive)|"
    r"do\s+not\s+(?:verify|check|report)",
    re.I,
)
PDF_ERRORS = (
    PdfminerException,
    PDFException,
    PDFSyntaxError,
    PSEOF,
    ValueError,
    TypeError,
    KeyError,
    OSError,
)


def valid_pdf(data: bytes) -> bool:
    return bool(data.startswith(b"%PDF-") and len(data) <= MAX_BYTES)


def fallback_pdf(data: bytes) -> ParseResult:
    if not valid_pdf(data):
        return ParseResult(
            status="FAILED", parser="pdfplumber", reasons=["invalid or oversized PDF"]
        )
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            sentences = []
            for page_no, page in enumerate(pdf.pages, 1):
                for part in re.split(r"(?<=[.!?])\s+|\n\s*\n", page.extract_text() or ""):
                    if part.strip():
                        sentences.append(
                            ParsedSentence(
                                id=f"s{len(sentences) + 1:05d}",
                                text=part.strip(),
                                section=f"Page {page_no}",
                            )
                        )
        return ParseResult(
            status="PARTIAL" if sentences else "FAILED",
            parser="pdfplumber",
            paper=ParsedPaper(sentences=sentences),
            reasons=["fallback text only; bibliography and citation links unavailable"],
        )
    except PDF_ERRORS:
        return ParseResult(status="FAILED", parser="pdfplumber", reasons=["PDF extraction failed"])


async def ingest_pdf(data: bytes, gateway: Gateway) -> ParseResult:
    if not valid_pdf(data):
        return ParseResult(status="FAILED", parser="grobid", reasons=["invalid or oversized PDF"])
    response = await gateway.request(
        "grobid",
        "/api/processFulltextDocument",
        method="POST",
        timeout=60,
        data={"consolidateCitations": "0", "includeRawCitations": "1", "segmentSentences": "1"},
        files={"input": ("paper.pdf", data, "application/pdf")},
    )
    result = parse_tei(response.content) if response.status == 200 and not response.error else None
    if result and result.status != "FAILED":
        return result
    fallback = await asyncio.to_thread(fallback_pdf, data)
    fallback.reasons.insert(0, response.error or "GROBID returned unusable output")
    return fallback


class _InvisibleText(PDFPageAggregator):
    """pdfplumber chars omit Tr; record it from PDFMiner's text rendering state."""

    def render_string(self, textstate, seq, ncs, graphicstate):
        self.mode = textstate.render
        return super().render_string(textstate, seq, ncs, graphicstate)

    def render_char(self, *args, **kwargs):
        advance = super().render_char(*args, **kwargs)
        if getattr(self, "mode", 0) == 3 and self.cur_item._objs:
            self.invisible.append(self.cur_item._objs[-1])
        return advance


def scan_hidden_text(data: bytes) -> HiddenScan:
    if not valid_pdf(data):
        return HiddenScan(status="CHECK_INCOMPLETE", reason="invalid or oversized PDF")
    spans = []
    try:
        manager = PDFResourceManager()
        device = _InvisibleText(manager, laparams=LAParams())
        interpreter = PDFPageInterpreter(manager, device)
        invisible_pages = []
        try:
            for page in PDFPage.get_pages(io.BytesIO(data)):
                device.invisible = []
                interpreter.process_page(page)
                invisible_pages.append(device.invisible[:])
        finally:
            device.close()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                for char in page.chars:
                    categories = []
                    fill = char.get("non_stroking_color")
                    channels = fill if isinstance(fill, list | tuple) else [fill]
                    white = (
                        len(channels) in (1, 3)
                        and all(isinstance(c, int | float) and c >= 0.98 for c in channels)
                    ) or (len(channels) == 4 and all(c <= 0.02 for c in channels))
                    if white:
                        categories.append("WHITE_FILL")
                    if char.get("size", 10) < 2:
                        categories.append("TINY_FONT")
                    if (
                        char["x0"] < 0
                        or char["x1"] > page.width
                        or char["top"] < 0
                        or char["bottom"] > page.height
                    ):
                        categories.append("OFF_PAGE")
                    if categories and char["text"].strip():
                        spans.append(
                            HiddenSpan(
                                page=page_no,
                                text=char["text"],
                                categories=categories,
                                bbox=tuple(float(char[k]) for k in ("x0", "top", "x1", "bottom")),
                                reason="unusual PDF styling; intent requires review",
                            )
                        )
                for char in invisible_pages[page_no - 1]:
                    if char.get_text().strip():
                        spans.append(
                            HiddenSpan(
                                page=page_no,
                                text=char.get_text(),
                                categories=["INVISIBLE_RENDER_MODE"],
                                bbox=(
                                    float(char.x0),
                                    float(page.height - char.y1),
                                    float(char.x1),
                                    float(page.height - char.y0),
                                ),
                                reason="text rendering mode 3; intent requires review",
                            )
                        )
                value = page.extract_text() or ""
                for match in INSTRUCTIONS.finditer(value):
                    spans.append(
                        HiddenSpan(
                            page=page_no,
                            text=match.group(),
                            categories=["INSTRUCTION_PATTERN"],
                            bbox=(0.0, 0.0, float(page.width), float(page.height)),
                            reason="instruction-like text; treated only as document data",
                        )
                    )
        return HiddenScan(status="COMPLETE", spans=spans)
    except PDF_ERRORS:
        return HiddenScan(status="CHECK_INCOMPLETE", reason="hidden-text inspection failed")
