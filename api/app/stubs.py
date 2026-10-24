"""Fixture-only lane implementations; selected explicitly by STUBS=1."""

import asyncio
import json
from pathlib import Path

from contracts.schema import (
    ClaimMap,
    ExistenceResult,
    HiddenTextFinding,
    Paper,
    RetractionResult,
    SourceDocument,
    SupportResult,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "pipeline" / "paper1.json"


class FixtureServices:
    def __init__(self):
        self.ingest = self.resolve = self.sources = self.verify = self.graph = self

    async def read(self, field, model, row_id=None):
        await asyncio.sleep(0.01)
        value = json.loads(FIXTURE.read_text())[field]
        if row_id is not None:
            value = next(
                row for row in value if row.get("reference_id", row.get("citation_id")) == row_id
            )
        return model.model_validate(value)

    async def parse_pdf(self, data):
        return await self.read("paper", Paper)

    async def scan_hidden_text(self, data):
        await asyncio.sleep(0.01)
        return [
            HiddenTextFinding.model_validate(row)
            for row in json.loads(FIXTURE.read_text())["hidden_text"]
        ]

    async def resolve_reference(self, reference):
        return await self.read("existence", ExistenceResult, reference.id)

    async def check_retraction(self, existence, paper_date):
        if existence.status not in ("VERIFIED", "VERIFIED_WITH_DISCREPANCIES"):
            return RetractionResult(
                reference_id=existence.reference_id, status="UNKNOWN", reason=existence.reason
            )
        return await self.read("retractions", RetractionResult, existence.reference_id)

    async def fetch_source(self, existence):
        if existence.status not in ("VERIFIED", "VERIFIED_WITH_DISCREPANCIES"):
            return SourceDocument(
                reference_id=existence.reference_id,
                evidence_level="METADATA_ONLY",
                status="CHECK_INCOMPLETE",
                reason=existence.reason,
            )
        return await self.read("sources", SourceDocument, existence.reference_id)

    async def verify_citation(self, citation, source):
        if source.status == "CHECK_INCOMPLETE":
            return SupportResult(
                citation_id=citation.id,
                label="NEEDS_REVIEW",
                evidence_strength="INSUFFICIENT",
                reason=source.reason,
                needs_review_reason=source.reason,
            )
        return await self.read("support", SupportResult, citation.id)

    async def build_claim_map(self, paper):
        return await self.read("claim_map", ClaimMap)

    async def __aexit__(self, *_):
        pass
