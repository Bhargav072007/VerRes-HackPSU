import assert from "node:assert/strict";
import { test } from "node:test";
import paper3 from "./fixtures/prod/paper3-job.json";
import paper2 from "./fixtures/prod/paper2-job.json";
import { citationSupportVerdict, citationVerdict, decodeReport, matchesFilter, reportCounts } from "../lib/report";
import { evidenceDetails } from "../lib/evidence";
import { claimGraph } from "../lib/claim-graph";

test("paper3 support survives UNKNOWN retractions across receipts, counts, filters and graph", () => {
  const report = decodeReport(paper3)!;
  assert.ok(report);
  for (const [id, expected] of [["c00001", "SUPPORTED"], ["c00003", "PARTIALLY_SUPPORTED"]]) {
    const citation = report.paper!.citations!.find(c => c.id === id)!;
    assert.equal(citationSupportVerdict(report, citation), expected);
    assert.equal(citationVerdict(report, citation), expected);
    assert.equal(evidenceDetails(report, citation).verdict, expected);
    assert.equal(evidenceDetails(report, citation).needsReview, null);
    assert.equal(matchesFilter([citationVerdict(report, citation)], "Needs review"), false);
    assert.equal(matchesFilter([citationVerdict(report, citation)], "Problems only"), expected !== "SUPPORTED");
  }
  assert.deepEqual(reportCounts(report).slice(0, 5), [5, 1, 1, 0, 1]);
  const graph = claimGraph(report);
  assert.equal(graph.nodes.filter(n => n.data.kind === "Source").length, 5);
  for (const [id, flag] of [["b3", "NOT_FOUND"], ["b4", "DOI_MISMATCH"]]) {
    const source = graph.nodes.find(n => n.id === `source:${id}`)!;
    assert.equal(source.data.flag, flag);
    assert.equal(source.data.receipts.length, 1);
  }
  assert.equal(graph.edges.find(e => e.id.endsWith(":c00001"))!.data!.verdict, "SUPPORTED");
  assert.equal(graph.edges.find(e => e.id.endsWith(":c00003"))!.data!.verdict, "PARTIALLY_SUPPORTED");
  report.existence = []; report.retractions = [];
  assert.equal(citationVerdict(report, report.paper!.citations![0]), "SUPPORTED");
});

test("paper2 retracts Wakefield, counts one retraction, and keeps edge support separate", () => {
  const report = decodeReport(paper2)!;
  assert.ok(report);
  assert.equal(reportCounts(report)[3], 1);
  for (const c of report.paper!.citations!.filter(c => c.reference_id === "b0")) assert.equal(citationVerdict(report, c), "RETRACTED");
  assert.equal(claimGraph(report).nodes.find(n => n.id === "source:b0")!.data.flag, "RETRACTED");
  const supported = report.paper!.citations!.find(c => c.id === "c00002")!;
  report.retractions!.find(r => r.reference_id === supported.reference_id)!.status = "RETRACTED";
  assert.equal(citationVerdict(report, supported), "RETRACTED");
  assert.equal(citationSupportVerdict(report, supported), "SUPPORTED");
  assert.equal(claimGraph(report).edges.find(e => e.id.endsWith(":c00002"))!.data!.verdict, "SUPPORTED");
});
