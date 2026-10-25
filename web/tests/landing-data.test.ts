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
