"""Implement Sources using the shared reference and evidence-level contracts."""

import asyncio
import hashlib

from api.app.providers.boundary import parsed_reference, receipt_urls, reference_work
from api.app.providers.http import Gateway
from api.app.resolve.existence import agrees, combine_works
from api.app.sources.acquire import PARTIAL_PDF_SECTION, acquire_source
from api.app.verify.retrieval import passages
from contracts.interfaces import Sources
from contracts.schema import (
    EvidenceLevel,
    ExistenceResult,
    ExistenceStatus,
    SourceDocument,
    SourcePassage,
)


class SourceService(Sources):
    def __init__(self, gateway: Gateway, *, crossref=None, openalex=None, arxiv=None):
        self.gateway = gateway
        self.crossref, self.openalex, self.arxiv = crossref, openalex, arxiv

    async def fetch_source(self, existence: ExistenceResult) -> SourceDocument:
        if (
            existence.status
            not in {ExistenceStatus.VERIFIED, ExistenceStatus.VERIFIED_WITH_DISCREPANCIES}
            or existence.matched_reference is None
            or existence.matched_reference.id != existence.reference_id
        ):
            return SourceDocument(
                reference_id=existence.reference_id,
                evidence_level=EvidenceLevel.METADATA_ONLY,
                status="CHECK_INCOMPLETE",
                reason="reference identity is not verified",
            )
        reference = existence.matched_reference
        work = reference_work(reference)
        requests = []
        if reference.doi:
            requests = [
                client.lookup(reference.doi)
                for client in (self.crossref, self.openalex)
                if client is not None
            ]
        elif reference.arxiv_id and self.arxiv:
            requests = [self.arxiv.lookup(reference.arxiv_id)]
        if requests:
            results = await asyncio.gather(*requests)
            matching = [
                w for r in results for w in r.works if agrees(parsed_reference(reference), w)
            ]
            if matching:
                work = combine_works([work, *matching])
        acquired = await acquire_source(work, self.gateway)
        if acquired.evidence_level == "NONE":
            return SourceDocument(
                reference_id=existence.reference_id,
                evidence_level=EvidenceLevel.METADATA_ONLY,
                status="CHECK_INCOMPLETE",
                reason=acquired.reason,
            )
        chunks = passages(acquired.text) if acquired.evidence_level == "FULL_TEXT" else []
        public_passages = [
            SourcePassage(
                passage_id=p.id,
                text=p.text,
                section=PARTIAL_PDF_SECTION if not acquired.whole_source else None,
            )
            for p in chunks
        ]
        if acquired.abstract:
            public_passages.append(
                SourcePassage(passage_id="abstract", text=acquired.abstract, section="Abstract")
            )
        canonical = "\n\n".join(p.text for p in public_passages if p.passage_id != "abstract")
        if not canonical:
            canonical = acquired.text
        return SourceDocument(
            reference_id=existence.reference_id,
            evidence_level=(
                EvidenceLevel.FULL_TEXT
                if acquired.evidence_level == "FULL_TEXT"
                else EvidenceLevel.ABSTRACT_ONLY
            ),
            passages=public_passages,
            url=(
                acquired.origin
                if acquired.origin and acquired.origin.startswith("https://")
                else next(iter(receipt_urls(work)), None)
            ),
            content_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
            reason=acquired.reason,
        )
