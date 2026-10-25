"""Offline, blind human review and evidence-bound export. Never loads proposed labels."""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from api.app.eval.bakeoff import EvalPair, Label, dataset_readiness, fingerprint, protocol_manifest
from api.app.eval.candidates import (
    HERE,
    ROOT,
    Candidate,
    EvidenceSource,
    canonical_source,
    normalized,
    read_jsonl,
    validate_candidates,
)
from api.app.ingest.models import Record
from api.app.sources.acquire import Source
from api.app.verify.gates import quote_matches
from api.app.verify.models import AtomicClaim, Function

HASH = r"^[0-9a-f]{64}$"
LAYOUT_IDS = {"bc-eval-019", "bc-eval-022", "bc-eval-023", "bc-eval-025", "bc-eval-026"}


class HumanReview(Record):
    candidate_id: str
    candidate_sha256: str = Field(pattern=HASH)
    source_receipt_sha256: str = Field(pattern=HASH)
    prepared_source_sha256: str = Field(pattern=HASH)
    annotation_status: Literal["PENDING", "APPROVED", "EXCLUDED"] = "PENDING"
    citation_function: Function | None = None
    claim: dict[str, str | None] | None = None
    human_label: Label | None = None
    labeled_by: str | None = None
    label_reason: str | None = None
    evidence_quote: str | None = None
    source_identity: Literal["MATCH", "DOI_MISMATCH", "UNCERTAIN"] | None = None
    human_attestation: bool = False
    reviewed_at: str | None = None


def record_hash(record: Record) -> str:
    return fingerprint(record.model_dump(mode="json"))


def load_corpus(
    *, root: Path = ROOT, here: Path = HERE, expected_count: int = 40
) -> tuple[list[Candidate], list[EvidenceSource], dict[str, Source]]:
    from api.app.eval.evidence import prepare_evidence

    candidates = read_jsonl(here / "candidates.jsonl", Candidate)
    sources = read_jsonl(here / "sources.jsonl", EvidenceSource)
    errors = validate_candidates(candidates, sources, root=root, expected_count=expected_count)
    if errors:
        raise ValueError("candidate evidence validation failed: " + "; ".join(errors))
    prepared = {canonical_source(s.id): prepare_evidence(s, root) for s in sources}
    return candidates, sources, prepared


def review_template(
    candidates: list[Candidate], sources: list[EvidenceSource], prepared: dict[str, Source]
) -> list[HumanReview]:
    lookup = {canonical_source(s.id): s for s in sources}
    return [
        HumanReview(
            candidate_id=c.id,
            candidate_sha256=record_hash(c),
            source_receipt_sha256=record_hash(lookup[canonical_source(c.source_id)]),
            prepared_source_sha256=record_hash(prepared[canonical_source(c.source_id)]),
        )
        for c in candidates
    ]


def review_packet(
    candidates: list[Candidate], sources: list[EvidenceSource], prepared: dict[str, Source]
) -> list[dict]:
    lookup = {canonical_source(s.id): s for s in sources}
    packet = []
    for c in candidates:
        receipt, source = (
            lookup[canonical_source(c.source_id)],
            prepared[canonical_source(c.source_id)],
        )
        flags = []
        if c.id in LAYOUT_IDS:
            flags.append(
                "PDF math/layout artifact: compare the PDF and supply a reviewed atomic claim."
            )
        if c.citing_sentence.count("[") > 1 or "," in c.citation_marker:
            flags.append(
                "Multiple references: review only the assertion attributed to this source."
            )
        if c.id in {"bc-eval-034", "bc-eval-035"}:
            flags.append(
                "This sentence describes other authors' citing behavior; inspect attribution."
            )
        if c.id == "bc-eval-040":
            flags.append(
                "Compare the original bibliography entry with the retrieved source identity."
            )
        initial_matches = quote_matches(c.source_quote, source.text)
        if not initial_matches:
            flags.append(
                "Initial quote is outside the prepared abstract; choose a reviewed abstract quote."
            )
        if receipt.coverage == "FULL_TEXT":
            flags.append(
                "PDF availability does not establish full coverage; judge input is abstract-only."
            )
        packet.append(
            {
                **{
                    k: v
                    for k, v in c.model_dump().items()
                    if k not in {"human_label", "labeled_by", "quote_role"}
                },
                "source_title": receipt.title,
                "source_url": receipt.url,
                "source_caution": receipt.caution,
                "prepared_scope": "ABSTRACT_ONLY"
                if source.evidence_level == "ABSTRACT"
                else "UNAVAILABLE",
                "initial_quote_in_prepared_source": initial_matches,
                "review_flags": flags,
            }
        )
    return packet


def review_issues(
    candidates: list[Candidate],
    sources: list[EvidenceSource],
    prepared: dict[str, Source],
    reviews: list[HumanReview],
) -> list[str]:
    expected = {r.candidate_id: r for r in review_template(candidates, sources, prepared)}
    errors = []
    ids = [r.candidate_id for r in reviews]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        errors.append("reviews must cover each candidate exactly once")
    for review in reviews:
        if review.candidate_id not in expected:
            continue
        for field in ("candidate_sha256", "source_receipt_sha256", "prepared_source_sha256"):
            if getattr(review, field) != getattr(expected[review.candidate_id], field):
                errors.append(f"stale {field}: {review.candidate_id}")
        if review.annotation_status != "APPROVED":
            errors.append(f"human review is {review.annotation_status}: {review.candidate_id}")
            continue
        if not review.human_attestation:
            errors.append(f"missing human attestation: {review.candidate_id}")
        annotator = (review.labeled_by or "").strip()
        if not annotator or annotator.casefold() in {
            "codex",
            "claude",
            "opus",
            "gpt",
            "fixture",
            "synthetic",
            "codex proposal; not a human annotation",
        }:
            errors.append(f"missing human annotator identity: {review.candidate_id}")
        if not review.human_label or not (review.label_reason or "").strip():
            errors.append(f"missing human label or reason: {review.candidate_id}")
        if not review.citation_function or not review.source_identity:
            errors.append(
                f"missing citation function or source identity review: {review.candidate_id}"
            )
        if review.source_identity == "UNCERTAIN" and review.human_label != "NEEDS_REVIEW":
            errors.append(f"uncertain source identity requires NEEDS_REVIEW: {review.candidate_id}")
        try:
            claim = AtomicClaim.model_validate(review.claim)
            if (
                not claim.text.strip()
                or not claim.subject_or_population.strip()
                or not claim.outcome.strip()
            ):
                raise ValueError("blank claim field")
        except (ValidationError, ValueError):
            errors.append(f"missing or invalid human-reviewed atomic claim: {review.candidate_id}")
        try:
            stamp = datetime.fromisoformat(review.reviewed_at or "")
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("timezone required")
        except ValueError:
            errors.append(f"missing timezone-aware human review time: {review.candidate_id}")
        c = next(c for c in candidates if c.id == review.candidate_id)
        source = prepared[canonical_source(c.source_id)]
        if source.evidence_level == "NONE":
            errors.append(f"prepared evidence unavailable: {review.candidate_id}")
        quote = review.evidence_quote or ""
        if normalized(quote) not in normalized(source.text) or not quote_matches(
            quote, source.text
        ):
            errors.append(f"reviewed quote absent from prepared evidence: {review.candidate_id}")
    return errors


def reviewed_pairs(candidates, sources, prepared, reviews) -> list[EvalPair]:
    errors = review_issues(candidates, sources, prepared, reviews)
    if errors:
        raise ValueError("human review is not export-ready: " + "; ".join(errors))
    by_id = {r.candidate_id: r for r in reviews}
    receipts = {canonical_source(s.id): s for s in sources}
    pairs = []
    for c in candidates:
        r, receipt = by_id[c.id], receipts[canonical_source(c.source_id)]
        pairs.append(
            EvalPair(
                id=c.id,
                paper_id=c.paper_id,
                citation_text=c.citing_sentence,
                claim=AtomicClaim.model_validate(r.claim),
                source=prepared[canonical_source(c.source_id)],
                human_label=r.human_label,
                labeled_by=r.labeled_by,
                label_reason=r.label_reason,
                synthetic=c.synthetic,
                citation_function=r.citation_function,
                evidence_quote=r.evidence_quote,
                provenance={
                    "candidate_sha256": record_hash(c),
                    "source_receipt_sha256": record_hash(receipt),
                    "source_id": canonical_source(c.source_id),
                    "source_artifact_sha256": receipt.sha256,
                    "review_sha256": record_hash(r),
                    "source_coverage": "ABSTRACT_ONLY",
                    "prepared_source_sha256": r.prepared_source_sha256,
                    "source_identity": r.source_identity,
                },
            )
        )
    errors = dataset_readiness(pairs)
    if errors:
        raise ValueError("benchmark is not ready: " + "; ".join(errors))
    return pairs


def jsonl(records: list) -> str:
    return "".join(
        json.dumps(
            r.model_dump(mode="json") if isinstance(r, Record) else r,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
        for r in records
    )


def prepare_bundle(output: Path, *, root: Path = ROOT, here: Path = HERE) -> dict:
    from api.app.eval.review_page import render_review_page

    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "output directory is not empty; preserve reviews or choose a new directory"
        )
    candidates, sources, prepared = load_corpus(root=root, here=here)
    reviews = review_template(candidates, sources, prepared)
    packet = review_packet(candidates, sources, prepared)
    output.mkdir(parents=True, exist_ok=True)
    (output / "reviews.jsonl").write_text(jsonl(reviews))
    (output / "review.html").write_text(
        render_review_page(packet, [r.model_dump() for r in reviews])
    )
    manifest = {
        "format_version": "bc-review-v1",
        "candidate_count": len(candidates),
        "human_labeled": 0,
        "benchmark_ready": False,
        "candidate_set_sha256": fingerprint([c.model_dump(mode="json") for c in candidates]),
        "source_receipts_sha256": fingerprint([s.model_dump(mode="json") for s in sources]),
        "synthetic_count": sum(c.synthetic for c in candidates),
        "prepared_scopes": {
            s.evidence_level: sum(v.evidence_level == s.evidence_level for v in prepared.values())
            for s in prepared.values()
        },
        "initial_quotes_outside_prepared_abstract": [
            p["id"] for p in packet if not p["initial_quote_in_prepared_source"]
        ],
        "unavailable_sources": [
            key for key, source in prepared.items() if source.evidence_level == "NONE"
        ],
        "reviews_sha256": hashlib.sha256((output / "reviews.jsonl").read_bytes()).hexdigest(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def export_reviewed(
    review_path: Path, output: Path, *, root: Path = ROOT, here: Path = HERE
) -> dict:
    if output.exists():
        raise ValueError("output already exists; choose a new versioned export directory")
    candidates, sources, prepared = load_corpus(root=root, here=here)
    reviews = read_jsonl(review_path, HumanReview)
    pairs = reviewed_pairs(candidates, sources, prepared, reviews)
    output.mkdir(parents=True)
    text = jsonl(pairs)
    (output / "pairs.jsonl").write_text(text)
    (output / "reviews.jsonl").write_bytes(review_path.read_bytes())
    manifest = {
        "format_version": "bc-bakeoff-v1",
        "benchmark_ready": True,
        "count": len(pairs),
        "pairs_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "reviews_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "candidate_set_sha256": fingerprint([c.model_dump(mode="json") for c in candidates]),
        "source_receipts_sha256": fingerprint([s.model_dump(mode="json") for s in sources]),
        "protocol": protocol_manifest(),
        "warning": "Human attestations are not authenticated. No model execution has occurred.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_export(
    export: Path, review_path: Path, *, root: Path = ROOT, here: Path = HERE
) -> list[EvalPair]:
    manifest = json.loads((export / "manifest.json").read_text())
    raw = (export / "pairs.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest.get("pairs_sha256"):
        raise ValueError("exported pair file hash changed")
    if hashlib.sha256(review_path.read_bytes()).hexdigest() != manifest.get("reviews_sha256"):
        raise ValueError("review file hash changed")
    candidates, sources, prepared = load_corpus(root=root, here=here)
    reviews = read_jsonl(review_path, HumanReview)
    expected = reviewed_pairs(candidates, sources, prepared, reviews)
    if (
        raw.decode() != jsonl(expected)
        or manifest.get("protocol") != protocol_manifest()
        or manifest.get("format_version") != "bc-bakeoff-v1"
        or manifest.get("benchmark_ready") is not True
        or manifest.get("count") != len(expected)
        or manifest.get("candidate_set_sha256")
        != fingerprint([c.model_dump(mode="json") for c in candidates])
        or manifest.get("source_receipts_sha256")
        != fingerprint([s.model_dump(mode="json") for s in sources])
    ):
        raise ValueError("export no longer matches reviewed evidence or the current judge protocol")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    prep = subs.add_parser("prepare")
    prep.add_argument("output", type=Path)
    status = subs.add_parser("status")
    status.add_argument("reviews", type=Path)
    export = subs.add_parser("export")
    export.add_argument("reviews", type=Path)
    export.add_argument("output", type=Path)
    verify = subs.add_parser("verify-export")
    verify.add_argument("output", type=Path)
    verify.add_argument("reviews", type=Path)
    rehearsal = subs.add_parser("rehearse")
    rehearsal.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare_bundle(args.output)
        elif args.command == "export":
            result = export_reviewed(args.reviews, args.output)
        elif args.command == "verify-export":
            result = {"verified_pairs": len(verify_export(args.output, args.reviews))}
        elif args.command == "rehearse":
            from api.app.eval.rehearsal import rehearse

            result = asyncio.run(rehearse(args.output))
        else:
            candidates, sources, prepared = load_corpus()
            reviews = read_jsonl(args.reviews, HumanReview)
            errors = review_issues(candidates, sources, prepared, reviews)
            result = {
                "benchmark_ready": not errors,
                "count": len(reviews),
                "approved": sum(r.annotation_status == "APPROVED" for r in reviews),
                "issues": errors,
            }
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, ValidationError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
