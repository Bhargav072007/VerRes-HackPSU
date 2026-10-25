import asyncio
import io

import pdfplumber
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams
from pdfminer.pdfexceptions import PDFException
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.psparser import PSEOF
from pdfplumber.utils.exceptions import PdfminerException

from api.app.ingest.basic import PAGE_LIMIT, PDF_LIMIT, fallback_pdf
from api.app.ingest.hidden import page_hidden_spans
from api.app.ingest.models import HiddenScan, ParseResult
from api.app.ingest.tei import parse_tei
from api.app.providers.http import Gateway

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
    return bool(data.startswith(b"%PDF-") and len(data) <= PDF_LIMIT)


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
        if getattr(self, "mode", 0) in (3, 7) and self.cur_item._objs:
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
            for index, page in enumerate(PDFPage.get_pages(io.BytesIO(data))):
                if index >= PAGE_LIMIT:
                    return HiddenScan(status="CHECK_INCOMPLETE", reason="PDF exceeds 80 pages")
                device.invisible = []
                interpreter.process_page(page)
                invisible_pages.append(device.invisible[:])
        finally:
            device.close()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                spans.extend(page_hidden_spans(page, page_no, invisible_pages[page_no - 1]))
        return HiddenScan(status="COMPLETE", spans=spans)
    except PDF_ERRORS:
        return HiddenScan(status="CHECK_INCOMPLETE", reason="hidden-text inspection failed")
