import assert from "node:assert/strict";
import { test } from "node:test";
import { claimGraph } from "../lib/claim-graph";
import { informationalOutcomes, reviewOutcome, sourceEvidenceLabel } from "../lib/review-outcome";
import { citationDisplayVerdict, citationVerdict, matchesFilter, reportCounts } from "../lib/report";
import { reviewFixture } from "./fixtures/review";

const background = "Background citation: no specific factual finding is attributed to this source.";
const method = "Method reference: this citation identifies a method or tool, not a specific finding.";

test("informational citations stay non-accusatory without being relabeled supported", () => {
  const report = reviewFixture();
  report.existence!.forEach(row => { row.status = "VERIFIED"; });
  report.retractions!.forEach(row => { row.status = "NONE"; });
  report.support!.forEach((row, i) => { row.label = "NEEDS_REVIEW"; row.evidence = []; row.reason = row.needs_review_reason = i % 2 ? method : background; });
  for (const citation of report.paper!.citations!) {
    assert.equal(citationVerdict(report, citation), "NEEDS_REVIEW");
    const display = citationDisplayVerdict(report, citation);
    assert.ok(informationalOutcomes.includes(display));
    assert.equal(matchesFilter([display], "Problems only"), false);
    assert.equal(matchesFilter([display], "Unresolved"), false);
  }
  assert.equal(reportCounts(report)[5], 0);
  const graphReceipts = claimGraph(report).nodes.filter(n => n.data.kind === "Source").flatMap(n => n.data.receipts);
  assert.equal(graphReceipts.length, report.paper!.citations!.length);
  assert.ok(graphReceipts.every(r => informationalOutcomes.includes(r.verdict)));
  report.existence![0].status = "DOI_MISMATCH";
  const affected = report.paper!.citations!.find(c => c.reference_id === report.existence![0].reference_id)!;
  assert.equal(citationDisplayVerdict(report, affected), "DOI_MISMATCH");
  assert.equal(matchesFilter([citationDisplayVerdict(report, affected)], "Problems only"), true);
});

test("service failure, missing adjudication and insufficient evidence are distinct", () => {
  for (const [reason, expected] of [
    ["judge model call failed (HTTP_429)", "CHECK_INCOMPLETE"],
    ["an eligible adjudicator is not configured (model/vendor/family policy)", "SECOND_CHECK_PENDING"],
    ["abstract does not address this claim; full text unavailable", "INSUFFICIENT_EVIDENCE"],
    ["models disagree or adjudicator evidence failed", "INSUFFICIENT_EVIDENCE"],
    ["The treatment failed to improve outcomes, but the evidence is indirect.", "INSUFFICIENT_EVIDENCE"],
    ["Source unavailable: publisher request failed", "CHECK_INCOMPLETE"],
  ]) {
    const status = reviewOutcome({ reason, needs_review_reason: reason });
    assert.equal(status, expected);
    assert.equal(matchesFilter([status], "Unresolved"), true);
  }
  assert.equal(reviewOutcome(), "CHECK_INCOMPLETE");
});

test("partial text coverage is explicit and unknown reasons do not imply a skipped check", () => {
  assert.equal(sourceEvidenceLabel({ reason: "Partial PDF text coverage: diagrams unavailable", evidence_level: "FULL_TEXT" }), "Extracted PDF text · partial coverage");
  assert.equal(sourceEvidenceLabel({ reason: "Matched", evidence_level: "ABSTRACT_ONLY" }), "Abstract only");
  assert.equal(sourceEvidenceLabel({ reason: "Matched", evidence_level: "FULL_TEXT" }), "Full text");
  assert.equal(sourceEvidenceLabel(null), "Metadata only");
  assert.equal(reviewOutcome({ reason: background + " Extra text.", needs_review_reason: null }), "INSUFFICIENT_EVIDENCE");
});
