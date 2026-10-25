"""Implementation of contracts.interfaces.Ingest; extraction details stay private."""

import asyncio
import hashlib

from api.app.ingest.pdf import ingest_pdf, scan_hidden_text
from api.app.providers.boundary import public_reference
from api.app.providers.http import Gateway
from contracts.interfaces import Ingest
from contracts.schema import Citation, HiddenTextFinding, Paper, Sentence


class IngestService(Ingest):
    def __init__(self, gateway: Gateway):
        self.gateway = gateway

    async def parse_pdf(self, data: bytes) -> Paper:
        parsed = await ingest_pdf(data, self.gateway)
        paper = parsed.paper
        citations = []
        for c in paper.citations:
            reference_text = c.reference_raw or c.reference_title or ""
            context = "\n".join(
                part
                for part in (
                    f"Marked reference {c.reference_id}: {reference_text}",
                    f"Citation marker: {c.marker}",
                    f"Section: {c.section}",
                    c.previous,
                    c.text,
                    c.next,
                )
                if part
            )
            citations.append(
                Citation(
                    id=c.id,
                    reference_id=c.reference_id,
                    sentence_ids=[c.sentence_id],
                    claim_text=c.text,
                    context=context,
                )
            )
        return Paper(
            id="paper-" + hashlib.sha256(data).hexdigest(),
            title=paper.title,
            paper_date=paper.published,
            sentences=[Sentence(id=s.id, text=s.text, section=s.section) for s in paper.sentences],
            references=[public_reference(r) for r in paper.references],
            citations=citations,
            status="PARSED" if parsed.status == "FULL" else "NEEDS_REVIEW",
            needs_review_reason="; ".join(parsed.reasons) or None,
        )

    async def scan_hidden_text(self, data: bytes) -> list[HiddenTextFinding]:
        result = await asyncio.to_thread(scan_hidden_text, data)
        if result.status != "COMPLETE":
            return [
                HiddenTextFinding(
                    id="scan-incomplete",
                    kind="CHECK_INCOMPLETE",
                    quote="",
                    reason=result.reason or "hidden-text inspection failed",
                )
            ]
        return [
            HiddenTextFinding(
                id=f"hidden-{i:05d}",
                page=span.page,
                quote=span.text,
                kind="SUSPICIOUS_TEXT"
                if span.categories == ["INSTRUCTION_PATTERN"]
                else "HIDDEN_TEXT",
                reason=f"{', '.join(span.categories)}: {span.reason}",
            )
            for i, span in enumerate(result.spans, 1)
        ]
