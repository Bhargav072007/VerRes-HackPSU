"""Exercise the real 40 candidate inputs with local fixture adapters, never paid models."""

import json
from pathlib import Path

from api.app.eval.bakeoff import EvalPair, run_bakeoff
from api.app.eval.candidates import canonical_source
from api.app.eval.reviews import load_corpus
from api.app.verify.models import AtomicClaim


class OfflineFixtureModel:
    vendor = "local-fixture"
    family = "deterministic-operational-fixture"

    def __init__(self, *, inject_faults: bool = False):
        self.model_id = "offline-fault-injection-v1" if inject_faults else "offline-abstention-v1"
        self.inject_faults = inject_faults
        self.calls = 0

    async def complete(self, **kwargs):
        self.calls += 1
        if kwargs.get("task") != "judge":
            raise ValueError("offline rehearsal only exercises the atomic judge task")
        if self.inject_faults and self.calls % 5 == 0:
            return "deliberately invalid fixture JSON"
        return json.dumps(
            {
                "label": "NEEDS_REVIEW",
                "evidence_strength": "INSUFFICIENT",
                "reason": "Local operational fixture; no scientific judgment or human annotation.",
                "evidence": [],
                "mismatch_types": [],
            }
        )


async def rehearse(output: Path) -> dict:
    if output.exists():
        raise ValueError("rehearsal report already exists; choose a new output path")
    candidates, _, prepared = load_corpus()
    pairs = [
        EvalPair(
            id=c.id,
            paper_id=c.paper_id,
            citation_text=c.citing_sentence,
            claim=AtomicClaim(
                text=c.citing_sentence,
                subject_or_population="UNREVIEWED OPERATIONAL PLACEHOLDER",
                exposure_or_intervention=None,
                outcome="UNREVIEWED OPERATIONAL PLACEHOLDER",
                direction="n.a.",
                magnitude=None,
                relation="descriptive",
                hedge="possible",
                scope_or_time=None,
            ),
            source=prepared[canonical_source(c.source_id)],
            synthetic=c.synthetic,
        )
        for c in candidates
    ]
    if any(p.source.evidence_level == "NONE" for p in pairs):
        raise ValueError("rehearsal requires genuine prepared evidence for every candidate")
    models = [OfflineFixtureModel(), OfflineFixtureModel(inject_faults=True)]
    report = await run_bakeoff(
        pairs, models, dataset_version="unlabeled-candidates-v1", rehearsal=True
    )
    report["operational_checks"] = {
        "candidate_inputs": len(pairs),
        "local_fixture_calls": sum(m.calls for m in models),
        "network_calls": 0,
        "paid_model_calls": 0,
        "fault_injection": "Every fifth response of fixture two is intentionally invalid JSON.",
        "claim_annotation": "Unreviewed citing sentences; no atomic ground truth.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report
