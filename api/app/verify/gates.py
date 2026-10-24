import re
import unicodedata

from rapidfuzz.fuzz import ratio

from api.app.sources.acquire import Source
from api.app.verify.models import Finding, Judgment, Passage

SEVERE = {"NOT_SUPPORTED", "CONTRADICTED"}


def normalize_quote(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(
        value.translate(
            str.maketrans(
                {
                    "\u2019": "'",
                    "\u2018": "'",
                    "\u201c": '"',
                    "\u201d": '"',
                    "\u2013": "-",
                    "\u2014": "-",
                }
            )
        ).split()
    )


def _protected(value: str) -> tuple[list[str], list[str]]:
    return (
        re.findall(r"\d+(?:[.,]\d+)*%?", value),
        re.findall(r"\b(?:not|no|never|neither|without|cannot|can't|didn't|doesn't)\b", value),
    )


def quote_matches(quote: str, passage: str) -> bool:
    quote, passage = normalize_quote(quote), normalize_quote(passage)
    if len(quote.split()) < 4:
        return False
    if quote in passage:
        return True
    words, wanted = passage.split(), quote.split()
    for length in range(max(1, len(wanted) - 1), len(wanted) + 2):
        for start in range(len(words) - length + 1):
            window = " ".join(words[start : start + length])
            if _protected(window) == _protected(quote) and ratio(quote, window) >= 95:
                return True
    return False


def uncertain(source: Source, reason: str, models: list[str] | None = None) -> Finding:
    return Finding(
        status="NEEDS_REVIEW",
        reason=reason,
        evidence_level=source.evidence_level,
        model_ids=models or [],
        source_work_id=source.work_id,
        source_origin=source.origin,
    )


def gate(
    judgment: Judgment, passages: list[Passage], source: Source, model_id: str, *, adjudicated=False
) -> Finding:
    if judgment.label == "NEEDS_REVIEW":
        return uncertain(source, judgment.reason, [model_id])
    if source.evidence_level == "NONE":
        return uncertain(source, "source evidence is unavailable", [model_id])
    if judgment.label in SEVERE and source.evidence_level != "FULL_TEXT":
        return uncertain(
            source, "abstract-only evidence cannot establish a severe finding", [model_id]
        )
    lookup = {p.id: p.text for p in passages}
    valid = [
        q
        for q in judgment.evidence
        if q.passage_id in lookup and quote_matches(q.quote, lookup[q.passage_id])
    ]
    if not valid or len(valid) != len(judgment.evidence):
        return uncertain(source, "evidence quote or passage could not be verified", [model_id])
    if judgment.evidence_strength == "INSUFFICIENT":
        return uncertain(source, "judge supplied no evidentiary support", [model_id])
    if judgment.label == "SUPPORTED" and judgment.evidence_strength != "DIRECT":
        return uncertain(source, "indirect evidence cannot establish full support", [model_id])
    if judgment.label in SEVERE and not adjudicated:
        return uncertain(
            source, "severe finding requires independent whole-source adjudication", [model_id]
        )
    return Finding(
        status=judgment.label,
        reason=judgment.reason,
        evidence=valid,
        evidence_level=source.evidence_level,
        evidence_strength=judgment.evidence_strength,
        model_ids=[model_id],
        source_work_id=source.work_id,
        source_origin=source.origin,
        passages=[p for p in passages if p.id in {q.passage_id for q in valid}],
        mismatch_types=judgment.mismatch_types,
    )


def aggregate(findings: list[Finding], source: Source) -> Finding:
    if not findings:
        return uncertain(source, "no verifiable atomic claims")
    rank = {
        "SUPPORTED": 0,
        "PARTIALLY_SUPPORTED": 1,
        "NEEDS_REVIEW": 2,
        "NOT_SUPPORTED": 3,
        "CONTRADICTED": 4,
    }
    return max(findings, key=lambda finding: rank[finding.status]).model_copy(deep=True)
