"""Claim-map implementation using A1's exact LLM/output schema."""

import re

from pydantic import ValidationError

from api.app.verify.model import Model, ModelFailure, call_model
from contracts.interfaces import Graph
from contracts.schema import ClaimMap, Paper


def validate_claim_map(proposed: ClaimMap, paper: Paper) -> ClaimMap:
    reasons = []
    ids, valid_nodes = set(), []
    sentences = {s.id for s in paper.sentences}
    citations = {c.id for c in paper.citations}
    for node in proposed.nodes:
        if (
            len(valid_nodes) >= 12
            or node.id in ids
            or not node.id
            or not node.text
            or len(node.text.split()) > 20
            or not node.sentence_ids
            or not set(node.sentence_ids) <= sentences
            or not set(node.citation_ids) <= citations
        ):
            reasons.append("invalid, duplicate or oversized node dropped")
            continue
        ids.add(node.id)
        valid_nodes.append(node)
    adjacency = {node.id: set() for node in valid_nodes}
    edges, seen = [], set()

    def reaches(start, target):
        pending, visited = [start], set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current not in visited:
                visited.add(current)
                pending.extend(adjacency[current])
        return False

    for edge in proposed.edges:
        key = (edge.source_id, edge.target_id, edge.relation)
        if (
            edge.source_id not in ids
            or edge.target_id not in ids
            or key in seen
            or reaches(edge.target_id, edge.source_id)
        ):
            reasons.append("invalid, duplicate or cyclic edge dropped")
            continue
        if edge.evidence:
            # No cited-source passages are supplied to graph extraction; it cannot verify
            # source quotes. Keep the structural relationship, remove invented receipts.
            edge = edge.model_copy(update={"evidence": []})
            reasons.append("unverifiable graph evidence removed")
        seen.add(key)
        adjacency[edge.source_id].add(edge.target_id)
        edges.append(edge)
    if proposed.paper_id != paper.id:
        reasons.append("model returned a different paper ID")
    if proposed.status == "NEEDS_REVIEW":
        reasons.append(proposed.needs_review_reason or "model could not complete the graph")
    if not valid_nodes:
        reasons.append("no grounded graph nodes")
    return ClaimMap(
        paper_id=paper.id,
        nodes=valid_nodes,
        edges=edges,
        status="NEEDS_REVIEW" if reasons else "COMPLETE",
        needs_review_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


class GraphService(Graph):
    def __init__(self, model: Model | None = None):
        self.model = model

    async def build_claim_map(self, paper: Paper) -> ClaimMap:
        selected = [
            s
            for s in paper.sentences
            if re.search(r"abstract|introduction|results|conclusion", s.section or "", re.I)
        ]
        if self.model is None or not selected:
            return ClaimMap(
                paper_id=paper.id,
                status="NEEDS_REVIEW",
                needs_review_reason="graph model or eligible numbered sentences unavailable",
            )
        try:
            result = await call_model(
                self.model,
                "claim_map",
                {
                    "paper_id": paper.id,
                    "sentences": [s.model_dump() for s in selected],
                    "citations": [c.model_dump() for c in paper.citations],
                },
                ClaimMap,
            )
        except (ModelFailure, ValidationError):
            return ClaimMap(
                paper_id=paper.id,
                status="NEEDS_REVIEW",
                needs_review_reason="claim map output failed schema validation",
            )
        return validate_claim_map(result, paper.model_copy(update={"sentences": selected}))
