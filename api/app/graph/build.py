import re
from typing import Literal

from pydantic import Field, ValidationError

from app.ingest.models import Paper, Record
from app.verify.model import Model, ModelFailure, call_model
from app.verify.models import CitationVerification


class Node(Record):
    id: str
    kind: Literal["MAIN_CLAIM", "FINDING", "METHOD", "BACKGROUND"]
    text: str
    sentence_ids: list[str]


class Edge(Record):
    source: str
    target: str
    kind: Literal["SUPPORTS", "DEPENDS_ON"]


class GraphProposal(Record):
    nodes: list[Node] = Field(max_length=12)
    edges: list[Edge] = Field(max_length=100)


class ClaimGraph(Record):
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    statuses: dict[str, str] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


def validate_graph(proposal: GraphProposal, paper: Paper) -> ClaimGraph:
    graph = ClaimGraph()
    valid = {s.id for s in paper.sentences}
    ids = set()
    for node in proposal.nodes:
        if (
            not node.id
            or node.id in ids
            or not node.sentence_ids
            or not set(node.sentence_ids) <= valid
            or not node.text.strip()
            or len(node.text.split()) > 20
        ):
            graph.reasons.append("invalid or duplicate graph node dropped")
            continue
        ids.add(node.id)
        graph.nodes.append(node)
    adjacency = {i: set() for i in ids}
    seen = set()

    def reaches(start, end):
        pending, visited = [start], set()
        while pending:
            current = pending.pop()
            if current == end:
                return True
            if current not in visited:
                visited.add(current)
                pending.extend(adjacency[current])
        return False

    for edge in proposal.edges:
        key = (edge.source, edge.target, edge.kind)
        if (
            edge.source not in ids
            or edge.target not in ids
            or key in seen
            or reaches(edge.target, edge.source)
        ):
            graph.reasons.append("invalid, duplicate or cyclic graph edge dropped")
            continue
        seen.add(key)
        adjacency[edge.source].add(edge.target)
        graph.edges.append(edge)
    return graph


async def build_graph(paper: Paper, model: Model) -> ClaimGraph:
    selected = [
        s
        for s in paper.sentences
        if re.search(r"abstract|introduction|results|conclusion", s.section, re.I)
    ]
    if not selected:
        return ClaimGraph(reasons=["no eligible numbered sentences"])
    try:
        proposal = await call_model(
            model, "graph", [s.model_dump() for s in selected], GraphProposal
        )
        # Only sentences actually supplied to the model may be used.
        return validate_graph(proposal, paper.model_copy(update={"sentences": selected}))
    except (ModelFailure, ValidationError):
        return ClaimGraph(reasons=["claim graph output failed schema validation"])


def color_graph(graph: ClaimGraph, paper: Paper, results: list[CitationVerification]) -> ClaimGraph:
    checked = {r.citation_id: r.finding.status for r in results}
    statuses = {}
    rank = {
        "SUPPORTED": 0,
        "PARTIALLY_SUPPORTED": 1,
        "NEEDS_REVIEW": 2,
        "NOT_SUPPORTED": 3,
        "CONTRADICTED": 4,
    }
    for node in graph.nodes:
        linked = [c.id for c in paper.citations if c.sentence_id in node.sentence_ids]
        if linked:
            statuses[node.id] = max((checked.get(c, "NEEDS_REVIEW") for c in linked), key=rank.get)
    return graph.model_copy(update={"statuses": statuses})
