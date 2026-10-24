"""Run with configured Model adapters via run_bakeoff; CLI manages human labels.

No demo papers or human labels were supplied, so pairs.jsonl is deliberately empty.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from api.app.ingest.models import Record
from api.app.sources.acquire import Source
from api.app.verify.gates import SEVERE, gate, quote_matches
from api.app.verify.model import Model, ModelFailure, call_model
from api.app.verify.models import AtomicClaim, Judgment
from api.app.verify.retrieval import retrieve

Label = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NEEDS_REVIEW"]


class EvalPair(Record):
    id: str
    paper_id: str
    citation_text: str
    claim: AtomicClaim
    source: Source
    human_label: Label | None = None
    labeled_by: str | None = None
    label_reason: str | None = None


class Prediction(Record):
    pair_id: str
    model_id: str
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
    severe_false_positives: int
    accuracy: float | None
    admitted_accuracy: float | None
    invalid_json_rate: float | None
    service_failure_rate: float | None
    quote_verification_failure_rate: float | None
    confusion: dict[str, int] = Field(default_factory=dict)


def read_pairs(path: Path) -> list[EvalPair]:
    pairs = [
        EvalPair.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]
    ids = [p.id for p in pairs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate evaluation pair IDs")
    return pairs


def summarize(pairs: list[EvalPair], predictions: list[Prediction]) -> Metrics:
    expected = {p.id: p for p in pairs}
    if {p.pair_id for p in predictions} != set(expected) or len(predictions) != len(pairs):
        raise ValueError("predictions must cover each evaluation pair exactly once")
    labeled = [
        p for p in predictions if expected[p.pair_id].human_label and expected[p.pair_id].labeled_by
    ]
    valid = [p for p in predictions if p.model_label is not None]
    total = len(predictions)
    correct = sum(p.model_label == expected[p.pair_id].human_label for p in labeled)
    admitted = sum(p.admitted_label == expected[p.pair_id].human_label for p in labeled)
    severe_fp = sum(
        p.model_label in SEVERE and expected[p.pair_id].human_label not in SEVERE for p in labeled
    )
    confusion = {}
    for p in labeled:
        key = f"{expected[p.pair_id].human_label}->{p.model_label or 'ERROR'}"
        confusion[key] = confusion.get(key, 0) + 1
    return Metrics(
        total=total,
        human_labeled=len(labeled),
        schema_valid=len(valid),
        severe_false_positives=severe_fp,
        accuracy=correct / len(labeled) if labeled else None,
        admitted_accuracy=admitted / len(labeled) if labeled else None,
        invalid_json_rate=sum(p.invalid_json for p in predictions) / total if total else None,
        service_failure_rate=sum(p.service_failure for p in predictions) / total if total else None,
        quote_verification_failure_rate=sum(p.quote_failure for p in valid) / len(valid)
        if valid
        else None,
        confusion=confusion,
    )


async def run_bakeoff(
    pairs: list[EvalPair], models: list[Model], *, dataset_version: str, output: Path | None = None
) -> dict:
    if len({model.model_id for model in models}) != len(models) or len(models) < 2:
        raise ValueError("at least two distinct candidate models are required")
    report = {
        "dataset_version": dataset_version,
        "dataset_sha256": hashlib.sha256(
            "\n".join(p.model_dump_json() for p in pairs).encode()
        ).hexdigest(),
        "prompt_version": "v2",
        "prompt_sha256": hashlib.sha256(
            (Path(__file__).parent.parent / "prompts" / "preamble.v1.md").read_bytes()
            + (Path(__file__).parent.parent / "prompts" / "judge.v2.md").read_bytes()
            + json.dumps(Judgment.model_json_schema(), sort_keys=True).encode()
        ).hexdigest(),
        "ran_at": datetime.now(UTC).isoformat(),
        "dataset_ready": len(pairs) == 40
        and len({p.paper_id for p in pairs}) == 3
        and all(p.human_label and p.labeled_by for p in pairs),
        "models": {},
    }
    for model in models:
        predictions = []
        for pair in pairs:
            selected = await asyncio.to_thread(
                retrieve, pair.claim.text, pair.source.text, pair.source.abstract
            )
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
                    pair_id=pair.id,
                    model_id=model.model_id,
                    model_label=judgment.label,
                    admitted_label=checked.status,
                    quote_failure=failed,
                    reason=checked.reason,
                )
            except ValidationError:
                prediction = Prediction(
                    pair_id=pair.id,
                    model_id=model.model_id,
                    invalid_json=True,
                    reason="invalid structured model output",
                )
            except ModelFailure:
                prediction = Prediction(
                    pair_id=pair.id,
                    model_id=model.model_id,
                    service_failure=True,
                    reason="model service failed",
                )
            predictions.append(prediction)
        report["models"][model.model_id] = {
            "family": model.family,
            "metrics": summarize(pairs, predictions).model_dump(),
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
        if not args.label or not args.annotator or not args.reason:
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
    print(
        json.dumps(
            {
                "total": len(pairs),
                "papers": len({p.paper_id for p in pairs}),
                "labeled": sum(bool(p.human_label and p.labeled_by) for p in pairs),
            }
        )
    )


if __name__ == "__main__":
    main()
