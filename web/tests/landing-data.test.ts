import assert from "node:assert/strict";
import { test } from "node:test";
import { countWord, heroCards, referenceChip } from "../lib/landing-data";
import { decodeReport } from "../lib/report";
import paper3 from "./fixtures/prod/paper3-job.json";

test("hero cards are the eight real references with fixture-derived verdict chips", () => {
  assert.equal(heroCards.length, 8);
  assert.deepEqual(heroCards.map(c => [c.author.split(" ")[0], c.year, c.chip]), [
    ["Wakefield", 1998, "RETRACTED"], ["Taylor", 2014, "SUPPORTED"], ["Lecun", 2015, "NEEDS_REVIEW"],
    ["Vaswani", 2017, "SUPPORTED"], ["Devlin", 2019, "PARTIALLY_SUPPORTED"], ["He", 2016, "NEEDS_REVIEW"],
    ["Kowalczyk", 2021, "NOT_FOUND"], ["Smith", 2019, "DOI_MISMATCH"],
  ]);
  assert.equal(countWord(heroCards.length), "Eight");
  assert.equal(countWord(40), "40");
});

test("a reference chip never claims support without verified evidence", () => {
  const report = decodeReport(structuredClone(paper3))!;
  report.support = report.support!.map(s => ({ ...s, evidence: [] }));
  assert.equal(referenceChip(report, "b1"), "NEEDS_REVIEW");
  assert.equal(referenceChip(report, "missing-id"), "NEEDS_REVIEW");
});

test("stepper demo cards come from the recorded runs", async () => {
  const { stepperDemo } = await import("../lib/landing-data");
  assert.deepEqual(stepperDemo.parse.map(l => l.line), [3, 4, 5, 6]);
  assert.deepEqual(stepperDemo.resolve.map(r => r.label), ["FOUND", "FOUND", "FOUND", "NOT FOUND", "DOI MISMATCH"]);
  const wakefield = stepperDemo.retraction.find(r => r.retracted)!;
  assert.match(wakefield.byline, /^Wakefield/);
  assert.equal(wakefield.year, "2010");
  assert.equal(wakefield.notice, "https://doi.org/10.1016/s0140-6736%2810%2960175-4");
  assert.equal(stepperDemo.retraction.filter(r => r.retracted).length, 1);
  assert.equal(stepperDemo.source.identifier, "arXiv:1810.04805");
  assert.match(stepperDemo.source.passage!, /^BERT is conceptually simple/);
  assert.equal(stepperDemo.verify.verdict, "PARTIALLY_SUPPORTED");
  assert.deepEqual(stepperDemo.review.panel.map(r => [r.id, r.name, r.major, r.minor]), [["R1", "Methods", 3, 0], ["R2", "Claims", 1, 0], ["R3", "Evidence", 4, 0]]);
  assert.match(stepperDemo.review.areaChair!, /BERT/);
});
