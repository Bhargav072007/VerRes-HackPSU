import asyncio
import re
import unicodedata
from typing import Literal

from pydantic import Field
from rapidfuzz.fuzz import token_set_ratio

from api.app.ingest.models import ParsedReference, Record
from api.app.providers.models import Work


class ExistenceResult(Record):
    status: Literal[
        "FOUND", "DOI_MISMATCH", "AMBIGUOUS", "NOT_FOUND", "CHECK_INCOMPLETE", "UNCHECKABLE"
    ]
    reason: str
    work: Work | None = None
    candidates: list[Work] = Field(default_factory=list)
    providers_checked: list[str] = Field(default_factory=list)


def normalize(value: str | None) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value or "").casefold()))


def title_similarity(left, right) -> float:
    return token_set_ratio(normalize(left), normalize(right)) / 100 if left and right else 0


def author_agrees(ref: ParsedReference, work: Work) -> bool:
    return bool(
        ref.authors and work.authors and normalize(ref.authors[0]) == normalize(work.authors[0])
    )


def agrees(ref: ParsedReference, work: Work) -> bool:
    return (
        title_similarity(ref.title, work.title) >= 0.90
        and author_agrees(ref, work)
        and ref.year is not None
        and work.year is not None
        and abs(ref.year - work.year) <= 1
    )


def metadata_mismatch(ref: ParsedReference, work: Work) -> bool:
    return bool(
        (ref.title and work.title and title_similarity(ref.title, work.title) < 0.9)
        or (ref.authors and work.authors and not author_agrees(ref, work))
        or (ref.year is not None and work.year is not None and abs(ref.year - work.year) > 1)
    )


def score(ref: ParsedReference, work: Work) -> float:
    year = ref.year is not None and work.year is not None and abs(ref.year - work.year) <= 1
    return (
        0.6 * title_similarity(ref.title, work.title)
        + 0.2 * author_agrees(ref, work)
        + 0.1 * year
        + 0.1 * title_similarity(ref.venue, work.venue)
    )


def combine_works(works: list[Work]) -> Work:
    """Preserve source-access metadata when providers corroborate the same identity."""
    best = next((w for w in works if w.oa_url), works[0])
    abstract_work = next((w for w in works if w.provider == "crossref" and w.abstract), None)
    abstract_work = abstract_work or next((w for w in works if w.abstract), best)
    index_work = next((w for w in works if w.abstract_inverted_index), best)
    origin = None
    if abstract_work.abstract:
        origin = abstract_work.abstract_origin or abstract_work.provider
    elif index_work.abstract_inverted_index:
        origin = index_work.abstract_origin or index_work.provider
    return best.model_copy(
        update={
            "abstract": abstract_work.abstract,
            "abstract_origin": origin,
            "abstract_inverted_index": index_work.abstract_inverted_index,
            "arxiv": next((w.arxiv for w in works if w.arxiv), best.arxiv),
        }
    )


async def resolve_reference(
    ref: ParsedReference, crossref, openalex, arxiv=None
) -> ExistenceResult:
    if ref.kind.lower() in {"book", "web", "website", "software", "dataset"}:
        return ExistenceResult(
            status="UNCHECKABLE", reason="reference type is outside index coverage"
        )
    direct = []
    if ref.doi:
        direct = await asyncio.gather(crossref.lookup(ref.doi), openalex.lookup(ref.doi))
    elif ref.arxiv and arxiv:
        direct = [await arxiv.lookup(ref.arxiv)]
    direct_works = [work for result in direct for work in result.works]
    matching = [work for work in direct_works if agrees(ref, work)]
    mismatching = [work for work in direct_works if metadata_mismatch(ref, work)]
    if matching and not mismatching:
        return ExistenceResult(
            status="FOUND",
            reason="identifier and bibliographic metadata agree",
            work=combine_works(matching),
            providers_checked=[r.provider for r in direct],
        )
    if matching and mismatching:
        return ExistenceResult(
            status="AMBIGUOUS",
            reason="identifier providers disagree",
            candidates=direct_works,
            providers_checked=[r.provider for r in direct],
        )
    if mismatching and ref.doi:
        return ExistenceResult(
            status="DOI_MISMATCH",
            reason="DOI resolves to conflicting metadata",
            candidates=mismatching,
            providers_checked=[r.provider for r in direct],
        )
    results = await asyncio.gather(crossref.search(ref.raw), openalex.search(ref.title or ref.raw))
    # Deduplicate provider copies only when both identifier AND metadata agree.
    candidates = []
    for result in results:
        for work in result.works:
            duplicate = next(
                (
                    other
                    for other in candidates
                    if (
                        work.doi
                        and work.doi == other.doi
                        and normalize(work.title) == normalize(other.title)
                        and work.year == other.year
                        and [normalize(a) for a in work.authors]
                        == [normalize(a) for a in other.authors]
                    )
                ),
                None,
            )
            if duplicate is None:
                candidates.append(work)
            else:
                candidates[candidates.index(duplicate)] = combine_works([duplicate, work])
    ranked = sorted(candidates, key=lambda w: score(ref, w), reverse=True)
    checked = list(dict.fromkeys(r.provider for r in direct + results))
    if ranked:
        best = score(ref, ranked[0])
        margin = best - score(ref, ranked[1]) if len(ranked) > 1 else best
        if best >= 0.85 and margin >= 0.10 - 1e-9:
            return ExistenceResult(
                status="FOUND",
                reason="bibliographic match meets score and margin",
                work=ranked[0],
                providers_checked=checked,
            )
        if best >= 0.75:
            return ExistenceResult(
                status="AMBIGUOUS",
                reason="candidate score or margin is insufficient",
                candidates=ranked,
                providers_checked=checked,
            )
    meaningful = len(normalize(ref.title).split()) >= 5
    indexable = ref.kind.lower() in {"journal-article", "proceedings-article", "preprint"}
    definitive = all(result.definitive for result in direct + results)
    if meaningful and indexable and definitive:
        names = ", ".join(checked)
        return ExistenceResult(
            status="NOT_FOUND",
            reason=f"Not found in queried providers: {names}.",
            providers_checked=checked,
        )
    return ExistenceResult(
        status="CHECK_INCOMPLETE",
        reason="provider failure, incomplete metadata, or uncertain index coverage",
        candidates=ranked,
        providers_checked=checked,
    )
