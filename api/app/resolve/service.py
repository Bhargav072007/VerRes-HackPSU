"""Contract-facing resolution and chronological retraction checks."""

from datetime import UTC, date, datetime

from api.app.providers.boundary import (
    parsed_reference,
    receipt_urls,
    reference_work,
    work_reference,
)
from api.app.providers.metadata import normalize_doi
from api.app.resolve.existence import agrees, combine_works, resolve_reference
from api.app.resolve.retraction import check_retraction, crossref_notices
from contracts.interfaces import Resolve
from contracts.schema import (
    ExistenceResult,
    ExistenceStatus,
    Reference,
    RetractionResult,
    RetractionStatus,
)


class ResolveService(Resolve):
    def __init__(self, crossref, openalex, *, arxiv=None, retractions=None):
        self.crossref, self.openalex = crossref, openalex
        self.arxiv, self.retractions = arxiv, retractions

    async def resolve_reference(self, reference: Reference) -> ExistenceResult:
        result = await resolve_reference(
            parsed_reference(reference), self.crossref, self.openalex, self.arxiv
        )
        work = result.work
        discrepancies = (
            ["reference DOI has invalid syntax"]
            if reference.doi and not normalize_doi(reference.doi)
            else []
        )
        provider_ids = {}
        if work:
            provider_ids[work.provider] = work.id
            if work.doi:
                provider_ids["doi"] = work.doi
            if work.arxiv:
                provider_ids["arxiv"] = work.arxiv
        return ExistenceResult(
            reference_id=reference.id,
            status=(
                ExistenceStatus.VERIFIED_WITH_DISCREPANCIES
                if discrepancies
                else ExistenceStatus.VERIFIED
            )
            if result.status == "FOUND"
            else ExistenceStatus(result.status),
            matched_reference=work_reference(work, reference.id) if work else None,
            candidates=[
                work_reference(w, f"{reference.id}-candidate-{i}")
                for i, w in enumerate(result.candidates, 1)
            ],
            provider_ids=provider_ids,
            discrepancies=discrepancies,
            receipt_urls=list(
                dict.fromkeys(
                    url
                    for candidate in ([work] if work else result.candidates)
                    for url in receipt_urls(candidate)
                )
            ),
            reason=result.reason,
        )

    async def check_retraction(
        self, existence: ExistenceResult, paper_date: date | None
    ) -> RetractionResult:
        if (
            existence.status
            not in {ExistenceStatus.VERIFIED, ExistenceStatus.VERIFIED_WITH_DISCREPANCIES}
            or existence.matched_reference is None
            or existence.matched_reference.id != existence.reference_id
        ):
            return RetractionResult(
                reference_id=existence.reference_id,
                status=RetractionStatus.UNKNOWN,
                reason="reference identity is not verified",
            )
        reference = existence.matched_reference
        work = reference_work(reference)
        if reference.doi:
            result = await self.openalex.lookup(reference.doi)
            matching = [
                w
                for w in result.works
                if w.doi == work.doi and agrees(parsed_reference(reference), w)
            ]
            if matching:
                work = combine_works([work, *matching])
                work.is_retracted = next(
                    (w.is_retracted for w in matching if w.is_retracted is not None), None
                )
        records = None
        if reference.doi and self.crossref:
            metadata = await self.crossref.lookup(reference.doi)
            originals = [w for w in metadata.works if w.doi == work.doi]
            if metadata.definitive and originals:
                records = crossref_notices(originals[0], work.doi)
                for record in list(records or []):
                    if record.retracted is None and record.notice_url:
                        notice = await self.crossref.lookup(record.notice_url)
                        for item in notice.works if notice.definitive else []:
                            if item.doi == normalize_doi(record.notice_url):
                                dated = crossref_notices(item, work.doi) or []
                                records.extend(r for r in dated if r.retracted is not None)
        watch_records = (
            await self.retractions.lookup(reference.doi)
            if self.retractions and reference.doi
            else None
        )
        if watch_records is not None:
            records = (records or []) + watch_records
        # Dated metadata supersedes an undated stub for the same notice.
        records = (
            [
                r
                for r in records
                if r.retracted is not None
                or not any(
                    d.notice_url == r.notice_url and d.retracted is not None for d in records
                )
            ]
            if records is not None
            else None
        )
        checked = check_retraction(work, paper_date, records)
        status = {
            "RETRACTED": RetractionStatus.RETRACTED,
            "NOT_RETRACTED": RetractionStatus.NONE,
            "CHECK_INCOMPLETE": RetractionStatus.UNKNOWN,
            "CORRECTED": RetractionStatus.CORRECTED,
            "EXPRESSION_OF_CONCERN": RetractionStatus.EXPRESSION_OF_CONCERN,
        }[checked.status]
        receipt = next(
            (
                r
                for r in checked.records
                if r.notice_type
                == {"RETRACTED": "RETRACTION", "CORRECTED": "CORRECTION"}.get(
                    checked.status, checked.status
                )
                and r.retracted
                and paper_date
                and r.retracted < paper_date
                and r.notice_url
            ),
            None,
        )
        return RetractionResult(
            reference_id=existence.reference_id,
            status=status,
            notice_urls=list(dict.fromkeys(r.notice_url for r in checked.records if r.notice_url)),
            checked_as_of=datetime.now(UTC).date(),
            reason=checked.reason,
            source_url=receipt.notice_url if receipt else None,
            source_type=(
                "crossref" if receipt.provenance.startswith("Crossref") else "retraction_watch"
            )
            if receipt
            else None,
        )
