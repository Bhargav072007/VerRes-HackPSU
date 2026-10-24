"""DOI diagnostics kept distinct from overall bibliographic existence."""

import asyncio
from typing import Literal

from pydantic import Field

from app.ingest.models import Record, Reference
from app.providers.metadata import normalize_doi
from app.providers.models import Work
from app.resolve.existence import agrees, metadata_mismatch


class DOICheck(Record):
    status: Literal[
        "MATCH", "DOI_MISMATCH", "INVALID", "UNRESOLVED", "AMBIGUOUS", "CHECK_INCOMPLETE"
    ]
    reason: str
    works: list[Work] = Field(default_factory=list)


async def check_doi(reference: Reference, crossref, openalex) -> DOICheck:
    if not reference.doi:
        return DOICheck(status="CHECK_INCOMPLETE", reason="reference has no DOI")
    if not normalize_doi(reference.doi):
        return DOICheck(status="INVALID", reason="identifier does not have DOI syntax")
    results = await asyncio.gather(crossref.lookup(reference.doi), openalex.lookup(reference.doi))
    works = [work for result in results for work in result.works]
    matches = [work for work in works if agrees(reference, work)]
    mismatches = [work for work in works if metadata_mismatch(reference, work)]
    if matches and mismatches:
        return DOICheck(
            status="AMBIGUOUS", reason="DOI providers return conflicting metadata", works=works
        )
    if mismatches:
        return DOICheck(
            status="DOI_MISMATCH", reason="DOI metadata conflicts with the reference", works=works
        )
    if matches:
        return DOICheck(
            status="MATCH", reason="DOI metadata agrees with the reference", works=works
        )
    if not works and all(result.definitive for result in results):
        return DOICheck(status="UNRESOLVED", reason="DOI was not found by either queried provider")
    return DOICheck(
        status="CHECK_INCOMPLETE", reason="DOI provider failure or incomplete metadata", works=works
    )
