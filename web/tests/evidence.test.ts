import assert from "node:assert/strict";
import { test } from "node:test";
import { evidenceDetails } from "../lib/evidence";
import { decodeReport } from "../lib/report";
import { evidenceFixture, evidenceStates } from "./fixtures/evidence";

test("evidence receipts preserve verdicts, exact quotes, specific reasons and safe links", () => {
  const report = evidenceFixture();
  assert.ok(decodeReport(report));
  report.paper.citations.forEach((c, i) => {
    const details = evidenceDetails(report, c);
    assert.equal(details.verdict, ["DOI_MISMATCH", "NOT_FOUND"].includes(evidenceStates[i]) ? "NEEDS_REVIEW" : evidenceStates[i]);
    assert.equal(details.quotes[0].quote, report.support[i].evidence[0].quote);
    assert.deepEqual(details.links.slice(0, 3).map(l => l.label), ["DOI", "OpenAlex", "Open-access copy / evidence"]);
    assert.equal(details.links.some(l => l.href.startsWith("javascript:")), false);
    assert.equal(details.agreement, i === 2 || i === 3 ? "2 of 2 models agree" : null);
  });
  assert.equal(evidenceDetails(report, report.paper.citations[4]).needsReview, "Abstract only: full text needed");
  report.support[2].adjudicated = false;
  assert.equal(evidenceDetails(report, report.paper.citations[2]).agreement, null);
  report.support[4].needs_review_reason = "models disagree or adjudicator evidence failed";
  assert.equal(evidenceDetails(report, report.paper.citations[4]).agreement, "Models disagree");
  report.support[0].evidence[0].quote = "Invented source quote.";
  const unverified = evidenceDetails(report, report.paper.citations[0]);
  assert.equal(unverified.verdict, "NEEDS_REVIEW");
  assert.deepEqual(unverified.quotes, []);
  assert.match(unverified.needsReview!, /could not be matched/);
  report.retractions = [];
  assert.equal(evidenceDetails(report, report.paper.citations[1]).verdict, "PARTIALLY_SUPPORTED");
  report.existence = report.existence.filter(e => e.reference_id !== "r-1");
  assert.equal(evidenceDetails(report, report.paper.citations[1]).verdict, "PARTIALLY_SUPPORTED");
  report.existence[0].receipt_urls = ["broken", "https://user:password@example.org", "data:text/html,test"];
  report.paper.references[0].doi = "\ud800";
  assert.doesNotThrow(() => evidenceDetails(report, report.paper.citations[0]));
});
test("newly rendered API fields reject malformed external data", () => {
  for (const mutation of [{ mismatch_types: [{}] }, { adjudicated: "yes" }, { needs_review_reason: {} }]) {
    const report = evidenceFixture(); Object.assign(report.support[0], mutation);
    assert.equal(decodeReport(report), null);
  }
  const report = evidenceFixture(); Object.assign(report.paper.citations[0], { claim_text: {} });
  assert.equal(decodeReport(report), null);
});

test("the evidence panel states each reason once", async () => {
  const { default: paper3 } = await import("./fixtures/prod/paper3-job.json");
  const report = decodeReport(structuredClone(paper3))!;
  const unverified = evidenceDetails(report, report.paper!.citations!.find(c => c.id === "c00005")!);
  assert.equal(unverified.needsReview, "reference identity is not verified");
  assert.deepEqual(unverified.reasons, ["Not found in queried providers: crossref, openalex."]);
  const fixture = evidenceFixture(), citation = fixture.paper.citations[0];
  fixture.support[0].reason = "Quote matches the claim.";
  fixture.existence.find(e => e.reference_id === citation.reference_id)!.reason = "quote matches the claim";
  assert.deepEqual(evidenceDetails(fixture, citation).reasons, ["Quote matches the claim."]);
});
