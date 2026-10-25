import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { decodeEvent, initialJob, jobCounts, jobReducer } from "../lib/job-stream";
import { liveFindings, liveGraph } from "../lib/live-findings";
const journal = (name: string) => readFileSync(`../fixtures/demo/${name}.jsonl`, "utf8").trim().split("\n").map(line => JSON.parse(line));

test("recorded receipts produce Wakefield, reference [4], DOI mismatch and hidden-text findings", () => {
  for (const name of ["paper2", "paper3"]) {
    const events = journal(name);
    for (const event of events) assert.ok(decodeEvent(event), `${name}: ${event.seq}`);
    const state = jobReducer(initialJob, { type: "snapshot", events });
    const model = liveFindings(state);
    assert.equal(jobCounts(state).checked, state.paper!.references!.length);
    assert.equal(jobReducer(state, { type: "snapshot", events }), state);
    assert.equal(model.findings.length, name === "paper2" ? 1 : 3);
    if (name === "paper2") {
      assert.equal(model.findings[0].verdict, "RETRACTED");
      assert.equal(model.findings[0].citationId, "c00001");
      assert.match(state.rows.b0.reference.authors!.join(" "), /Wakefield/);
    } else {
      assert.deepEqual(model.findings.map(f => f.id), ["existence:b4", "existence:b3", "hidden_text:hidden-00001"]);
      assert.match(model.findings[1].sentence, /Reference \[4\].*not found in Crossref, OpenAlex or arXiv/);
      assert.equal(model.findings[2].hiddenId, "1-0");
      assert.equal(model.quotes, 3);
    }
    const graph = liveGraph(state, model.report);
    assert.equal(graph.nodes.filter(n => n.data.kind !== "Source").length, state.claimMap!.nodes!.length);
  }
});

test("quiet state, incremental graph and exact quote checks never invent progress or verdicts", () => {
  assert.deepEqual(liveFindings(initialJob).findings, []);
  assert.equal(liveFindings(initialJob).quotes, 0);
  assert.deepEqual(liveGraph(initialJob, liveFindings(initialJob).report).nodes, []);
  const events = journal("paper3"), parsed = jobReducer(initialJob, { type: "snapshot", events: events.slice(0, 5) });
  assert.equal(liveGraph(parsed, liveFindings(parsed).report).nodes.filter(n => n.data.kind !== "Source").length, 6);
  const state = jobReducer(initialJob, { type: "snapshot", events }), support = structuredClone(state.support);
  support.c00001.label = "CONTRADICTED";
  assert.equal(liveFindings({ ...state, support }).findings.find(f => f.id === "support:c00001")!.verdict, "NEEDS_REVIEW");
  const rows = structuredClone(state.rows); rows.b0.existence!.status = "VERIFIED"; rows.b0.retraction!.status = "NONE";
  let model = liveFindings({ ...state, rows, support });
  assert.equal(model.findings.find(f => f.id === "support:c00001")!.verdict, "CONTRADICTED");
  support.c00001.evidence![0].quote = "This quote is absent from the source.";
  model = liveFindings({ ...state, rows, support });
  assert.equal(model.findings.find(f => f.id === "support:c00001")!.verdict, "NEEDS_REVIEW");
  assert.equal(model.quotes, 2);
  const graph = liveGraph({ ...state, rows, support }, model.report);
  assert.equal(graph.edges.find(e => e.id.includes("c00001"))!.data!.verdict, "NEEDS_REVIEW");
  assert.equal(decodeEvent({ seq: 1, type: "source", payload: { reference_id: "b0", status: "AVAILABLE", evidence_level: { toString: null } } }), null);
  for (const type of ["hidden_text", "source", "claim_map"]) for (const payload of [{}, { id: {}, kind: "HIDDEN_TEXT" }, { status: { toString: null } }]) assert.equal(decodeEvent({ seq: 1, type, payload }), null);
});
