import { test } from "node:test";
import assert from "node:assert/strict";
import { parseReaderSettings, readerDefaults } from "../lib/reader-settings";
import demo from "../fixtures/demo/paper3.json";
import { decodeReport, verifiedEvidence, type Citation } from "../lib/report";
test("reader preferences tolerate malformed storage and constrain every setting", () => {
  for (const value of [null, "dark", [], { size: NaN }, { size: Infinity }]) assert.deepEqual(parseReaderSettings(value), readerDefaults);
  assert.deepEqual(parseReaderSettings({ size: 99, spacing: "open", theme: "dark", width: "wide", font: "sans", reduceMotion: true }), { size: 22, spacing: "open", theme: "dark", width: "wide", font: "sans", reduceMotion: true });
  assert.equal(parseReaderSettings({ size: 1 }).size, 14);
  assert.deepEqual(parseReaderSettings({ spacing: "invalid", theme: "invalid", width: "invalid", font: "invalid", reduceMotion: "true" }), readerDefaults);
});
test("landing fixture quotes have unchanged verbatim source passages", () => {
  const report = decodeReport(demo); assert.ok(report);
  for (const id of ["c00001", "c00002"]) {
    const citation: Citation | undefined = report.paper?.citations?.find(c => c.id === id); assert.ok(citation);
    assert.ok(verifiedEvidence(report, citation).length);
  }
});
