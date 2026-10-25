import re
import unicodedata

from api.app.sources.acquire import Source
from api.app.verify.models import Finding, Judgment, Passage

SEVERE = {"NOT_SUPPORTED", "CONTRADICTED"}


def normalize_quote(value: str) -> str:
    # Preserve case: scientific units such as mM and mm are not interchangeable.
    # Compatibility folding would also turn 10⁵ into 105, changing the magnitude.
    value = unicodedata.normalize("NFC", value)
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


def quote_matches(quote: str, passage: str) -> bool:
    quote, passage = normalize_quote(quote), normalize_quote(passage)
    if len(quote.split()) < 4:
        return False
    # Edit similarity cannot establish a verbatim receipt: a single character can
    # invert a result. Boundaries also prevent quoting "effective" from "ineffective".
    for match in re.finditer(r"(?<!\w)" + re.escape(quote) + r"(?!\w)", passage):
        before, after = passage[: match.start()], passage[match.end() :]
        if quote[0].isdigit() and before and before[-1] in "+-−⁺⁻.,/%":
            continue
        if quote[-1].isdigit() and after and (after[0] in "%/^" or re.match(r"[.,]\d", after)):
            continue
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
    if len(judgment.evidence) > 3:
        return uncertain(source, "judge returned more than three evidence quotes", [model_id])
    if judgment.label == "NOT_SUPPORTED" and not source.whole_source:
        return uncertain(
            source,
            "extracted text cannot establish absence; complete source coverage needed",
            [model_id],
        )
    if judgment.label == "NOT_SUPPORTED" and source.evidence_level == "ABSTRACT":
        return uncertain(
            source, "abstract does not address this claim; full text unavailable", [model_id]
        )
    if (
        judgment.label == "CONTRADICTED"
        and source.evidence_level == "ABSTRACT"
        and (
            judgment.evidence_strength != "DIRECT" or set(judgment.mismatch_types) != {"DIRECTION"}
        )
    ):
        return uncertain(
            source, "abstract evidence does not establish an explicit opposite finding", [model_id]
        )
    if judgment.label in SEVERE and source.evidence_level not in {"FULL_TEXT", "ABSTRACT"}:
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
            source,
            "severe finding requires independent adjudication of the supplied evidence",
            [model_id],
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
