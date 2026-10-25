"""Explicitly injected single-judge bakeoff; never creates clients or reads credentials.

Benchmark execution requires reviewed, evidence-backed pairs. ``rehearsal=True`` is
an operational check only: reports always suppress scientific accuracy in that mode.
Unreviewed candidates are never silently promoted into benchmark ground truth.
"""

import argparse
import asyncio
import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from api.app.ingest.models import Record
from api.app.sources.acquire import Source
from api.app.verify.gates import SEVERE, gate, quote_matches
from api.app.verify.model import PROMPT_VERSIONS, Model, ModelFailure, call_model, output_schema
from api.app.verify.models import AtomicClaim, Function, Judgment
from api.app.verify.retrieval import retrieve

Label = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NEEDS_REVIEW"]
PAPERS = ("paper1_attention", "paper2_retracted_reference", "paper3_planted_problems")
HASH_KEYS = ("candidate_sha256", "source_receipt_sha256", "source_artifact_sha256", "review_sha256")


class EvalPair(Record):
    id: str
    paper_id: str
    citation_text: str
    claim: AtomicClaim
    source: Source
    human_label: Label | None = None
    labeled_by: str | None = None
    label_reason: str | None = None
    synthetic: bool | None = None
    citation_function: Function | None = None
    evidence_quote: str | None = None
    provenance: dict[str, str] = Field(default_factory=dict)


class Prediction(Record):
    pair_id: str
    model_id: str
    vendor: str | None = None
    model_label: Label | None = None
    admitted_label: Label = "NEEDS_REVIEW"
    invalid_json: bool = False
    service_failure: bool = False
    quote_failure: bool = False
    reason: str


class Metrics(Record):
    total: int
    human_labeled: int
    schema_valid: int
    severe_false_positives: int  # Backwards-compatible alias for the raw count.
    raw_severe_false_positives: int
    admitted_severe_false_positives: int
    nonsevere_human_labeled: int
    raw_severe_false_positive_rate: float | None
    admitted_severe_false_positive_rate: float | None
    accuracy: float | None
    admitted_accuracy: float | None
    invalid_json_rate: float | None
    service_failure_rate: float | None
    quote_verification_failure_rate: float | None
    confusion: dict[str, int] = Field(default_factory=dict)  # Raw alias.
    raw_confusion: dict[str, int] = Field(default_factory=dict)
    admitted_confusion: dict[str, int] = Field(default_factory=dict)


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def canonical_source(value: str) -> str:
    value = value.strip().casefold()
    value = re.sub(r"^https://(?:dx\.)?doi.org/", "doi:", value)
    value = re.sub(r"^https://arxiv.org/(?:abs|pdf)/", "arxiv:", value)
    if value.startswith("10."):
        value = "doi:" + value
    if value.startswith("arxiv:"):
        value = re.sub(r"v\d+$", "", value.removesuffix(".pdf"))
    return value


def pair_key(pair: EvalPair) -> tuple[str, str, str]:
    return (
        pair.paper_id,
        normalized(pair.citation_text).casefold(),
        canonical_source(pair.source.work_id),
    )


def human_labeled(pair: EvalPair) -> bool:
    return bool(
        pair.human_label and (pair.labeled_by or "").strip() and (pair.label_reason or "").strip()
    )


def dataset_readiness(pairs: list[EvalPair]) -> list[str]:
    """Return all readiness issues before any model adapter can be called."""
    issues = []
    if len(pairs) != 40:
        issues.append(f"expected 40 reviewed pairs; found {len(pairs)}")
    if {p.paper_id for p in pairs} != set(PAPERS):
        issues.append("pairs must cover the exact three fixture papers")
    ids, keys = set(), set()
    for pair in pairs:
        if not pair.id.strip() or pair.id in ids:
            issues.append(f"blank or duplicate pair ID: {pair.id}")
        ids.add(pair.id)
        key = pair_key(pair)
        if key in keys:
            issues.append(f"duplicate normalized citation/source pair: {pair.id}")
        keys.add(key)
        if not human_labeled(pair):
            issues.append(f"missing human label, annotator or reason: {pair.id}")
        if pair.citation_function is None:
            issues.append(f"missing reviewed citation function: {pair.id}")
        if pair.synthetic is not (pair.paper_id != PAPERS[0]):
            issues.append(f"missing or incorrect synthetic flag: {pair.id}")
        if not pair.citation_text.strip():
            issues.append(f"missing citation sentence: {pair.id}")
        source = pair.source
        if (
            source.evidence_level == "NONE"
            or len(source.text.split()) < 4
            or not source.work_id.strip()
            or not (source.origin or "").strip()
        ):
            issues.append(f"missing source evidence or origin: {pair.id}")
        if not pair.evidence_quote or not quote_matches(pair.evidence_quote, source.text):
            issues.append(f"missing or unverified reviewed evidence quote: {pair.id}")
        for field in HASH_KEYS:
            if not re.fullmatch(r"[0-9a-f]{64}", pair.provenance.get(field, "")):
                issues.append(f"missing or invalid provenance {field}: {pair.id}")
        if canonical_source(pair.provenance.get("source_id", "")) != canonical_source(
            source.work_id
        ):
            issues.append(f"provenance source identity does not match: {pair.id}")
        coverage = {"FULL_TEXT": "FULL_TEXT", "ABSTRACT": "ABSTRACT_ONLY"}.get(
            source.evidence_level
        )
        if not coverage or pair.provenance.get("source_coverage") != coverage:
            issues.append(f"provenance source coverage does not match: {pair.id}")
    return issues


def read_pairs(path: Path) -> list[EvalPair]:
    pairs = [
        EvalPair.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]
    if len({p.id for p in pairs}) != len(pairs):
        raise ValueError("duplicate evaluation pair IDs")
    if len({pair_key(p) for p in pairs}) != len(pairs):
        raise ValueError("duplicate normalized citation/source pairs")
    return pairs


def summarize(
    pairs: list[EvalPair], predictions: list[Prediction], *, scientific_accuracy: bool = True
) -> Metrics:
    expected = {p.id: p for p in pairs}
    if (
        len(expected) != len(pairs)
        or {p.pair_id for p in predictions} != set(expected)
        or len(predictions) != len(pairs)
    ):
        raise ValueError("predictions must cover each evaluation pair exactly once")
    if len({(p.vendor, p.model_id) for p in predictions}) > 1:
        raise ValueError("summarize accepts predictions from one model identity only")
    labeled = [p for p in predictions if human_labeled(expected[p.pair_id])]
    valid = [p for p in predictions if p.model_label is not None]
    total = len(predictions)
    nonsevere = [p for p in labeled if expected[p.pair_id].human_label not in SEVERE]
    raw_fp = sum(p.model_label in SEVERE for p in nonsevere)
    admitted_fp = sum(p.admitted_label in SEVERE for p in nonsevere)
    raw, admitted = {}, {}
    for prediction in labeled:
        label = expected[prediction.pair_id].human_label
        for counts, actual in (
            (raw, prediction.model_label or "ERROR"),
            (admitted, prediction.admitted_label),
        ):
            key = f"{label}->{actual}"
            counts[key] = counts.get(key, 0) + 1
    return Metrics(
        total=total,
        human_labeled=len(labeled),
        schema_valid=len(valid),
        severe_false_positives=raw_fp,
        raw_severe_false_positives=raw_fp,
        admitted_severe_false_positives=admitted_fp,
        nonsevere_human_labeled=len(nonsevere),
        raw_severe_false_positive_rate=raw_fp / len(nonsevere)
        if nonsevere and scientific_accuracy
        else None,
        admitted_severe_false_positive_rate=admitted_fp / len(nonsevere)
        if nonsevere and scientific_accuracy
        else None,
        accuracy=sum(p.model_label == expected[p.pair_id].human_label for p in labeled)
        / len(labeled)
        if labeled and scientific_accuracy
        else None,
        admitted_accuracy=sum(p.admitted_label == expected[p.pair_id].human_label for p in labeled)
        / len(labeled)
        if labeled and scientific_accuracy
        else None,
        invalid_json_rate=sum(p.invalid_json for p in predictions) / total if total else None,
        service_failure_rate=sum(p.service_failure for p in predictions) / total if total else None,
        quote_verification_failure_rate=sum(p.quote_failure for p in valid) / len(valid)
        if valid
        else None,
        confusion=raw,
        raw_confusion=raw,
        admitted_confusion=admitted,
    )


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def protocol_manifest() -> dict:
    prompts = Path(__file__).parent.parent / "prompts"
    prompt_version = PROMPT_VERSIONS["judge"]
    prompt = (
        (prompts / "preamble.v1.md").read_text()
        + "\n"
        + (prompts / f"judge.{prompt_version}.md").read_text()
    )
    schema = output_schema("judge", Judgment)
    retrieval = {
        "algorithm": "bm25s",
        "package_version": version("bm25s"),
        "passage_words": 200,
        "top_k": 8,
        "stopwords": "en",
        "append_abstract_if_absent": True,
        "implementation_sha256": hashlib.sha256(
            (Path(__file__).parent.parent / "verify/retrieval.py").read_bytes()
        ).hexdigest(),
    }
    return {
        "prompt_version": prompt_version,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "schema_sha256": fingerprint(schema),
        "retrieval": retrieval,
        "retrieval_sha256": fingerprint(retrieval),
    }


async def run_bakeoff(
    pairs: list[EvalPair],
    models: list[Model],
    *,
    dataset_version: str,
    output: Path | None = None,
    rehearsal: bool = False,
) -> dict:
    issues = dataset_readiness(pairs)
    if issues and not rehearsal:
        raise ValueError("dataset is not benchmark-ready: " + "; ".join(issues))
    if not dataset_version.strip():
        raise ValueError("dataset_version must be nonblank")
    identities = [
        ((getattr(m, "vendor", None) or "").strip().casefold(), m.model_id.strip()) for m in models
    ]
    if len(set(identities)) != len(models) or len(models) < 2:
        raise ValueError("at least two distinct vendor/model_id identities are required")
    if any(not model.model_id.strip() or not model.family.strip() for model in models):
        raise ValueError("model IDs and families must be nonblank")
    if not rehearsal and any(not vendor for vendor, _ in identities):
        raise ValueError("benchmark models require an explicit vendor identity")
    protocol = protocol_manifest()
    report = {
        "report_schema_version": "bakeoff.v3",
        "dataset_version": dataset_version,
        "dataset_sha256": fingerprint([p.model_dump(mode="json") for p in pairs]),
        **protocol,
        "protocol_sha256": fingerprint(protocol),
        "ran_at": datetime.now(UTC).isoformat(),
        "mode": "operational_rehearsal" if rehearsal else "reviewed_benchmark",
        "scope": "atomic_claim_single_judge; severe findings remain unadjudicated",
        "dataset_composition": {
            "citation_functions": {
                function: sum(p.citation_function == function for p in pairs)
                for function in ("SPECIFIC_CLAIM", "METHOD_OR_TOOL", "BACKGROUND", "CONTRAST")
            },
            "evidence_levels": {
                level: sum(p.source.evidence_level == level for p in pairs)
                for level in ("FULL_TEXT", "ABSTRACT", "NONE")
            },
        },
        "scientific_accuracy": not rehearsal,
        "dataset_ready": not issues and not rehearsal,
        "benchmark_ready": not issues and not rehearsal,
        "readiness_issues": issues,
        "models": {},
    }
    unique_ids = len({model.model_id for model in models}) == len(models)
    for model in models:
        predictions = []
        for pair in pairs:
            selected = await asyncio.to_thread(
                retrieve, pair.claim.text, pair.source.text, pair.source.abstract
            )
            metadata = {
                "pair_id": pair.id,
                "model_id": model.model_id,
                "vendor": getattr(model, "vendor", None),
            }
            try:
                judgment = await call_model(
                    model,
                    "judge",
                    {
                        "claim": pair.claim.model_dump(),
                        "evidence_level": pair.source.evidence_level,
                        "passages": [p.model_dump() for p in selected],
                    },
                    Judgment,
                )
                lookup = {p.id: p.text for p in selected}
                failed = (judgment.label != "NEEDS_REVIEW" and not judgment.evidence) or any(
                    q.passage_id not in lookup or not quote_matches(q.quote, lookup[q.passage_id])
                    for q in judgment.evidence
                )
                checked = gate(judgment, selected, pair.source, model.model_id)
                prediction = Prediction(
                    **metadata,
                    model_label=judgment.label,
                    admitted_label=checked.status,
                    quote_failure=failed,
                    reason=checked.reason,
                )
            except ValidationError:
                prediction = Prediction(
                    **metadata, invalid_json=True, reason="invalid structured model output"
                )
            except ModelFailure:
                prediction = Prediction(
                    **metadata, service_failure=True, reason="model service failed"
                )
            predictions.append(prediction)
        strata = {}
        for name, synthetic in (("real", False), ("synthetic", True), ("unspecified", None)):
            subset = [p for p in pairs if p.synthetic is synthetic]
            ids = {p.id for p in subset}
            strata[name] = summarize(
                subset,
                [p for p in predictions if p.pair_id in ids],
                scientific_accuracy=not rehearsal,
            ).model_dump()
        key = (
            model.model_id
            if unique_ids
            else json.dumps([getattr(model, "vendor", None), model.model_id])
        )
        report["models"][key] = {
            "model_id": model.model_id,
            "family": model.family,
            "vendor": getattr(model, "vendor", None),
            "metrics": summarize(
                pairs, predictions, scientific_accuracy=not rehearsal
            ).model_dump(),
            "strata": strata,
            "predictions": [p.model_dump() for p in predictions],
        }
    if output:
        await asyncio.to_thread(output.write_text, json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="Inspect or human-label evaluation JSONL")
    parser.add_argument("pairs", type=Path)
    parser.add_argument("--label-id")
    parser.add_argument(
        "--label",
        choices=[
            "SUPPORTED",
            "PARTIALLY_SUPPORTED",
            "NOT_SUPPORTED",
            "CONTRADICTED",
            "NEEDS_REVIEW",
        ],
    )
    parser.add_argument("--annotator")
    parser.add_argument("--reason")
    args = parser.parse_args()
    pairs = read_pairs(args.pairs)
    if args.label_id:
        if any(pair.provenance for pair in pairs):
            parser.error("provenance-bound pairs must be changed through reviewed export")
        if not args.label or not (args.annotator or "").strip() or not (args.reason or "").strip():
            parser.error("labeling requires --label, --annotator and --reason")
        pair = next((p for p in pairs if p.id == args.label_id), None)
        if pair is None:
            parser.error("unknown pair ID")
        pair.human_label, pair.labeled_by, pair.label_reason = (
            args.label,
            args.annotator,
            args.reason,
        )
        args.pairs.write_text("\n".join(p.model_dump_json() for p in pairs) + "\n")
    issues = dataset_readiness(pairs)
    print(
        json.dumps(
            {
                "total": len(pairs),
                "papers": len({p.paper_id for p in pairs}),
                "labeled": sum(human_labeled(p) for p in pairs),
                "benchmark_ready": not issues,
                "readiness_issues": issues,
            }
        )
    )


if __name__ == "__main__":
    main()
