"""Structural async interfaces; callers inject implementations or fixture stubs.

External-data failures must be represented by contract statuses and reasons.
Provider/model instructions must never be taken from paper or source text.
"""

from datetime import date
from typing import Protocol

from contracts.schema import (
    Citation,
    ClaimMap,
    ExistenceResult,
    HiddenTextFinding,
    Paper,
    Reference,
    RetractionResult,
    ReviewSummary,
    SourceDocument,
    SupportResult,
)


class Ingest(Protocol):
    async def parse_pdf(self, data: bytes) -> Paper: ...
    async def scan_hidden_text(self, data: bytes) -> list[HiddenTextFinding]: ...


class Resolve(Protocol):
    async def resolve_reference(self, reference: Reference) -> ExistenceResult: ...
    async def check_retraction(
        self, existence: ExistenceResult, paper_date: date | None
    ) -> RetractionResult: ...


class Sources(Protocol):
    async def fetch_source(self, existence: ExistenceResult) -> SourceDocument: ...


class Verify(Protocol):
    async def verify_citation(
        self, citation: Citation, source: SourceDocument
    ) -> SupportResult: ...


class Graph(Protocol):
    async def build_claim_map(self, paper: Paper) -> ClaimMap: ...


class Review(Protocol):
    async def run_review_panel(
        self, paper: Paper, support: list[SupportResult]
    ) -> ReviewSummary: ...
