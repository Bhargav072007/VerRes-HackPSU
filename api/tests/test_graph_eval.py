from pathlib import Path

import pytest

from api.app.eval.bakeoff import EvalPair, Prediction, read_pairs, run_bakeoff, summarize
from api.app.graph.build import Edge, GraphProposal, Node, build_graph, color_graph, validate_graph
from api.app.ingest.models import ParsedPaper, ParsedSentence
from api.app.verify.gates import uncertain
from api.app.verify.models import CitationVerification
from api.tests.helpers import FixtureModel, judgment


def test_graph_drops_invalid_ids_duplicates_and_cycles():
    paper = ParsedPaper(
        sentences=[ParsedSentence(id="s1", text="A valid claim.", section="Results")]
    )
    nodes = [
        Node(id="a", kind="FINDING", text="First finding", sentence_ids=["s1"]),
        Node(id="b", kind="MAIN_CLAIM", text="Main claim", sentence_ids=["s1"]),
        Node(id="invalid", kind="BACKGROUND", text="Wrong", sentence_ids=["missing"]),
    ]
    edges = [
        Edge(source="a", target="b", kind="SUPPORTS"),
        Edge(source="a", target="b", kind="SUPPORTS"),
        Edge(source="b", target="a", kind="DEPENDS_ON"),
        Edge(source="invalid", target="a", kind="SUPPORTS"),
    ]
    result = validate_graph(GraphProposal(nodes=nodes + [nodes[0]], edges=edges), paper)
    # Two invalid nodes and three rejected edges each produce a diagnostic.
    assert len(result.nodes) == 2 and len(result.edges) == 1 and len(result.reasons) == 5
    assert not result.statuses


async def test_graph_build_and_color(citation, source):
    paper = ParsedPaper(
        sentences=[ParsedSentence(id="s1", text=citation.text, section="Results")],
        citations=[citation],
    )
    model = FixtureModel(
        {
            "graph": {
                "nodes": [
                    {"id": "a", "kind": "FINDING", "text": "A finding", "sentence_ids": ["s1"]}
                ],
                "edges": [],
            }
        }
    )
    graph = await build_graph(paper, model)
    result = CitationVerification(citation_id="c1", finding=uncertain(source, "pending"))
    assert color_graph(graph, paper, [result]).statuses == {"a": "NEEDS_REVIEW"}
    assert not graph.statuses


async def test_graph_invalid_output_and_no_eligible_sentences():
    paper = ParsedPaper(sentences=[ParsedSentence(id="s1", text="Text", section="References")])
    assert (await build_graph(paper, FixtureModel({}))).reasons
    paper.sentences[0].section = "Results"
    assert (await build_graph(paper, FixtureModel({"graph": "not JSON"}))).reasons


async def test_bakeoff_records_actual_fixture_outcomes(claim, source, tmp_path):
    pairs = [
        EvalPair(
            id="a",
            paper_id="paper1",
            citation_text=claim.text,
            claim=claim,
            source=source,
            human_label="SUPPORTED",
            labeled_by="test fixture author",
        )
    ]
    models = [
        FixtureModel({"judge": judgment().model_dump()}, model_id="model1"),
        FixtureModel({"judge": "bad json"}, model_id="model2"),
    ]
    path = tmp_path / "report.json"
    report = await run_bakeoff(pairs, models, dataset_version="synthetic-test-only", output=path)
    assert path.exists() and not report["dataset_ready"]
    assert report["models"]["model1"]["metrics"]["accuracy"] == 1
    assert report["models"]["model2"]["metrics"]["invalid_json_rate"] == 1
    assert report["models"]["model2"]["metrics"]["accuracy"] == 0


def test_metrics_severe_false_positive_and_no_labels(claim, source):
    pairs = [
        EvalPair(
            id="a",
            paper_id="p",
            citation_text=claim.text,
            claim=claim,
            source=source,
            human_label="SUPPORTED",
            labeled_by="fixture",
        )
    ]
    predictions = [
        Prediction(pair_id="a", model_id="m", model_label="CONTRADICTED", reason="fixture")
    ]
    assert summarize(pairs, predictions).severe_false_positives == 1
    pairs[0].labeled_by = None
    assert summarize(pairs, predictions).accuracy is None
    assert summarize([], []).invalid_json_rate is None


def test_empty_dataset_and_duplicate_pair_ids(claim, source, tmp_path):
    assert read_pairs(Path(__file__).parents[1] / "app/eval/pairs.jsonl") == []
    pair = EvalPair(id="a", paper_id="p", citation_text=claim.text, claim=claim, source=source)
    target = tmp_path / "pairs.jsonl"
    target.write_text(pair.model_dump_json() + "\n" + pair.model_dump_json())
    with pytest.raises(ValueError, match="duplicate"):
        read_pairs(target)
