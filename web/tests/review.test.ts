import assert from "node:assert/strict";
import { test } from "node:test";
import { decodeReport } from "../lib/report";
import { decodeEvent } from "../lib/job-stream";
import { applyReviewEvent, fixTarget, hasReviewReceipt, isReviewComment, isReviewSummary, reviewComments, reviewState } from "../lib/review";
import { reviewFixture } from "./fixtures/review";
import { emptyProvenance } from "./fixtures/provenance";

test("panel fixture uses verified receipts, exact suggestion links and deduplicated reviewer comments", () => {
  const report = reviewFixture(), comment = report.review_comments![0];
  assert.equal(reviewComments(report).length, 3);
  assert.ok(isReviewComment(comment)); assert.ok(isReviewSummary(report.review));
  assert.ok(hasReviewReceipt(report, { ...comment, quote: "Treatment   improved outcomes in adults." }));
  assert.equal(hasReviewReceipt(report, { ...comment, quote: "Invented quote" }), false);
  assert.equal(hasReviewReceipt(report, { ...comment, sentence_ids: ["missing"] }), false);
  assert.equal(fixTarget(report, comment.suggestion), "sentence-s1");
  assert.equal(fixTarget(report, report.review_comments![2].suggestion), "citation-cite-2");
  assert.equal(fixTarget(report, "No matching suggestion"), undefined);
});
test("malformed review data stays isolated; old jobs hide the panel and warning meanings remain distinct", () => {
  const report = reviewFixture();
  const incomplete = decodeReport({ ...report, review_comments: [null] })!;
  assert.ok(reviewState(incomplete).failed); assert.deepEqual(incomplete.paper, report.paper);
  assert.equal(reviewState({ ...report, review: undefined, review_comments: [], stages: [] }).present, false);
  assert.equal(reviewState({ ...report, review: { ...emptyProvenance, warning: "Review panel unavailable" } }).hidden, false);
  assert.ok(reviewState({ ...report, review: { ...emptyProvenance, warning: "This paper contains hidden text addressed to AI reviewers." } }).hidden);
  assert.ok(reviewState({ ...report, stages: [{ stage: "run_review_panel", status: "CHECK_INCOMPLETE", reason: null }] }).failed);
  for (const payload of [{ comments: [null] }, { top_fixes: [5] }, { warning: {} }]) {
    assert.equal(isReviewSummary(payload), false);
    assert.equal(decodeEvent({ seq: 1, type: "review_summary", payload }), null);
  }
  assert.equal(decodeEvent({ seq: 1, type: "review", payload: {} }), null);
});
test("review and summary events update the running panel without replacing citation data", () => {
  const report = reviewFixture(), comment = report.review_comments![0];
  let running = { ...report, status: "RUNNING" as const, review: undefined, review_comments: [] } as typeof report;
  assert.ok(reviewState(running).running);
  for (const [type, payload] of [["review", comment], ["review_summary", report.review], ["hidden_text", { id: "h1", kind: "HIDDEN_TEXT", quote: "Recorded hidden text", reason: "Needs review", page: 1 }], ["stage", { stage: "run_review_panel", status: "COMPLETED" }]] as const) {
    running = applyReviewEvent(running, decodeEvent({ type, payload, seq: 1 })!);
  }
  assert.equal(reviewState(running).running, false); assert.ok(reviewState(running).hidden);
  assert.equal(running.paper, report.paper); assert.equal(running.review_comments!.length, 1);
});
