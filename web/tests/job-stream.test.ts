import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { decodeEvent, initialJob, jobCounts, jobReducer } from "../lib/job-stream";
const events = readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));

test("snapshot restore and duplicate native replay keep rows and counters idempotent", () => {
  const snapshot = { type: "snapshot" as const, events: events.slice(0, 31) };
  const state = jobReducer(initialJob, snapshot);
  assert.equal(Object.keys(state.rows).length, 3);
  assert.equal(jobCounts(state).checked, 4);
  assert.equal(jobCounts(state).missing, 0);
  assert.equal(state.rows['ref-2'].existence?.status, 'VERIFIED');
  assert.equal(jobReducer(state, snapshot), state);
  const complete = jobReducer(state, { type: "snapshot", events });
  assert.deepEqual(jobCounts(complete), { checked: 4, total: 4, missing: 0, retracted: 0, overstated: 0, needsReview: 1 });
  assert.equal(complete.done, true);
  assert.equal(Object.keys(complete.errors).length, 0);
  assert.equal(jobReducer(complete, { type: "snapshot", events }), complete);
  assert.equal(jobReducer(complete, { type: "reset" }), initialJob);
  const interrupted = jobReducer(state, { type: "notice", reason: "Reconnecting" });
  assert.equal(jobReducer(interrupted, { type: "snapshot", events }).errors.connection, undefined);
});
test("invalid external events stay incomplete without throwing or erasing receipts", () => {
  for (const event of events) assert.ok(decodeEvent(event), `seq ${event.seq}`);
  const state = jobReducer(initialJob, { type: "snapshot", events: events.slice(0, 3) });
  for (const bad of [null, {}, {seq: 2, type: 'paper', payload: {references: [null]}}, {seq: 3, type: 'existence', payload: {reference_id:'r', status:'GUESS', reason:'bad'}}, {seq:4,type:'existence',payload:{reference_id:'r',status:'VERIFIED',reason:'bad',receipt_urls:{}}}, {seq: 5, type:'support', payload: {citation_id:'c',label:'SUPPORTED',reason:'no quotes'}}]) {
    assert.equal(decodeEvent(bad), null);
    const next = jobReducer(state, { type: "snapshot", events: [bad] });
    assert.equal(next.rows, state.rows);
    assert.match(next.errors.connection, /CHECK_INCOMPLETE/);
  }
});
