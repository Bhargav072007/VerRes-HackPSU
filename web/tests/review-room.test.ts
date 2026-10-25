import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { initialJob, jobReducer } from "../lib/job-stream";
import { deriveRoom } from "../lib/review-room";

const events = readFileSync("../fixtures/demo/paper3.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));
const replay = (upTo: number) => jobReducer(initialJob, { type: "snapshot", events: events.slice(0, upTo) }).log;
const state = (room: ReturnType<typeof deriveRoom>, id: string) => room.agents.find(a => a.id === id)!;

test("paper 3's recorded events drive every agent to a terminal state", () => {
  const room = deriveRoom(replay(events.length));
  assert.equal(room.done, true);
  assert.deepEqual(room.agents.map(a => [a.id, a.status]), [["parser", "DONE"], ["hidden", "FLAGGED"], ["claims", "DONE"], ["resolver", "FLAGGED"], ["retraction", "DONE"], ["source", "DONE"], ["verifier", "DONE"], ["CLAIMS", "DONE"], ["METHODS", "DONE"], ["EVIDENCE", "DONE"], ["chair", "DONE"]]);
  assert.equal(state(room, "parser").finding, "Extracted 10 sentences · 5 references");
  assert.deepEqual([state(room, "resolver").done, state(room, "resolver").total, state(room, "verifier").total], [5, 5, 6]);
  assert.deepEqual(room.agents.filter(a => ["CLAIMS", "METHODS", "EVIDENCE"].includes(a.id)).map(a => a.done), ["CLAIMS", "METHODS", "EVIDENCE"].map(r => events.filter(e => e.type === "review" && e.payload.reviewer === r).length));
  assert.deepEqual(room.progress, { completed: 29, total: 29 });
  assert.deepEqual(room.slots.map(s => s.chip), ["PARTIALLY_SUPPORTED", "PARTIALLY_SUPPORTED", "NEEDS_REVIEW", "NOT_FOUND", "DOI_MISMATCH"]);
  assert.ok(room.feed.some(r => r.text === "[4] Kowalczyk 2021 Not found in Crossref, OpenAlex, arXiv" && r.chip === "NOT_FOUND"));
  assert.ok(room.elapsed > 0);
});

test("mid-run, only agents with started events work and nothing is invented", () => {
  const firstExistence = events.findIndex(e => e.type === "stage" && e.payload.stage.startsWith("existence:"));
  const room = deriveRoom(replay(firstExistence + 1));
  assert.equal(room.done, false);
  assert.equal(state(room, "resolver").status, "WORKING");
  assert.equal(state(room, "verifier").status, "QUEUED");
  assert.equal(state(room, "chair").status, "QUEUED");
  assert.equal(room.slots.every(s => s.chip === null), true);
  assert.equal(room.progress.completed < room.progress.total!, true);
});

test("a failed stage marks its agent Needs review with the event's reason, and the run continues", () => {
  const failed = events.map(e => e.type === "stage" && e.payload.stage === "source:b1" && e.payload.status === "COMPLETED" ? { ...e, payload: { ...e.payload, status: "CHECK_INCOMPLETE", reason: "source fetch timed out" } } : e);
  const room = deriveRoom(jobReducer(initialJob, { type: "snapshot", events: failed }).log);
  assert.equal(state(room, "source").status, "NEEDS_REVIEW");
  assert.equal(state(room, "source").reason, "source fetch timed out");
  assert.equal(state(room, "chair").status, "DONE");
});
