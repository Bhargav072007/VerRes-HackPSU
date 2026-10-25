import assert from "node:assert/strict";
import { test } from "node:test";
import { claimGraph } from "../lib/claim-graph";
import { decodeReport } from "../lib/report";
import { claimGraphFixture } from "./fixtures/claim-graph";
import { evidenceFixture, evidenceStates } from "./fixtures/evidence";
import { emptyProvenance } from "./fixtures/provenance";

test("fixture graph lays out claims left of deduplicated sources and preserves citation receipts", () => {
  const report = claimGraphFixture(), graph = claimGraph(report);
  assert.equal(graph.nodes.length, 5); assert.equal(graph.edges.length, 4);
  assert.equal(graph.nodes.find(n => n.id === "source:ref-1")!.data.receipts.length, 2);
  for (const e of graph.edges) assert.ok(graph.nodes.find(n => n.id === e.source)!.position.x < graph.nodes.find(n => n.id === e.target)!.position.x);
  assert.deepEqual(graph.edges.map(e => e.data!.verdict), ["SUPPORTED", "SUPPORTED", "NOT_SUPPORTED", "NEEDS_REVIEW"]);
  assert.equal(graph.edges[2].data!.receipts[0].quotes[0].quote, "children were not enrolled.");
  report.support![0].evidence![0].quote = "Unverifiable quote";
  assert.equal(claimGraph(report).edges[1].data!.verdict, "NEEDS_REVIEW");
  assert.deepEqual(claimGraph(report).edges[1].data!.receipts[0].quotes, []);
});
test("source alerts remain distinct from support verdicts; empty, missing and dangling maps stay safe", () => {
  const report = evidenceFixture();
  report.claim_map = { ...emptyProvenance, paper_id: "fixture", status: "COMPLETE", needs_review_reason: null, nodes: report.paper.citations.map(c => ({ ...emptyProvenance, id: c.id, text: c.claim_text, sentence_ids: c.sentence_ids!, citation_ids: [c.id], kind: "CLAIM" as const })), edges: [] };
  const graph = claimGraph(report);
  assert.deepEqual(graph.edges.map(e => e.data!.verdict), evidenceStates.map(s => ["DOI_MISMATCH", "RETRACTED", "NOT_FOUND"].includes(s) ? "NEEDS_REVIEW" : s));
  assert.deepEqual(graph.nodes.filter(n => n.data.flag).map(n => n.data.flag), ["DOI_MISMATCH", "RETRACTED", "NOT_FOUND"]);
  const claimMap = report.claim_map!;
  claimMap.edges = [{ ...emptyProvenance, source_id: "c-0", target_id: "c-1", relation: "SUPPORTS", reason: "Related", evidence: [{ ...emptyProvenance, passage_id: "p1", quote: "Unverified edge quote" }] }, { ...emptyProvenance, source_id: "missing", target_id: "c-1", relation: "DEPENDS_ON", reason: "Unavailable" }];
  const related = claimGraph(report);
  assert.equal(related.unlinked, true);
  assert.equal(related.edges.at(-1)!.data!.verdict, "NEEDS_REVIEW");
  assert.ok(!JSON.stringify(related).includes("Unverified edge quote"));
  claimMap.nodes = []; assert.equal(claimGraph(report).nodes.length, report.paper.references.length);
  report.claim_map = null; assert.equal(claimGraph(report).edges.length, 0);
});
test("claim map decoding rejects malformed external fields and keeps missing maps optional", () => {
  const report = claimGraphFixture();
  for (const map of [[], { ...report.claim_map, nodes: [null] }, { ...report.claim_map, nodes: [{ ...report.claim_map!.nodes![0], text: {} }] }, { ...report.claim_map, edges: [{ source_id: "x", target_id: "y", relation: "SUPPORTS", reason: "", evidence: [null] }] }]) assert.equal(decodeReport({ ...report, claim_map: map }), null);
  for (const field of ["status", "kind", "relation"]) {
    const map: Record<string, unknown> = { ...report.claim_map, [field]: { toString: null } };
    if (field === "kind") map.nodes = [{ ...report.claim_map!.nodes![0], kind: { toString: null } }];
    if (field === "relation") map.edges = [{ source_id: "x", target_id: "y", relation: { toString: null }, reason: "" }];
    assert.equal(decodeReport({ ...report, claim_map: map }), null);
  }
  assert.ok(decodeReport({ ...report, claim_map: null }));
  assert.ok(decodeReport({ ...report, claim_map: undefined }));
});
