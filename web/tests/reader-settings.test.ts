import { test } from "node:test";
import assert from "node:assert/strict";
import { parseReaderSettings, readerDefaults } from "../lib/reader-settings";
import { scrollBeats } from "../lib/scroll-beats";
import demo from "../fixtures/demo/paper3.json";
import { decodeReport, verifiedEvidence, type Citation } from "../lib/report";
test("reader preferences tolerate malformed storage and constrain every setting", () => {
  for (const value of [null, "dark", [], { size: NaN }, { size: Infinity }]) assert.deepEqual(parseReaderSettings(value), readerDefaults);
  assert.deepEqual(parseReaderSettings({ size: 99, spacing: "open", theme: "dark", width: "wide", font: "sans", reduceMotion: true }), { size: 22, spacing: "open", theme: "dark", width: "wide", font: "sans", reduceMotion: true });
  assert.equal(parseReaderSettings({ size: 1 }).size, 14);
  assert.deepEqual(parseReaderSettings({ spacing: "invalid", theme: "invalid", width: "invalid", font: "invalid", reduceMotion: "true" }), readerDefaults);
});
test("each 60vh beat animates over 42vh then holds for 18vh, and reverses exactly", () => {
  for (let i = 0; i < 5; i++) {
    assert.ok(scrollBeats((i + .35) / 5)[i] > .49 && scrollBeats((i + .35) / 5)[i] < .51);
    assert.equal(scrollBeats((i + .75) / 5)[i], 1);
    assert.equal(scrollBeats((i + .95) / 5)[i], 1);
    assert.ok(scrollBeats((i + .1) / 5)[i] < .15);
  }
  assert.deepEqual(scrollBeats(NaN), [0, 0, 0, 0, 0]);
  assert.deepEqual(scrollBeats(2), [1, 1, 1, 1, 1]);
});
test("landing fixture quotes have unchanged verbatim source passages", () => {
  const report = decodeReport(demo); assert.ok(report);
  for (const id of ["c00001", "c00002"]) {
    const citation: Citation | undefined = report.paper?.citations?.find(c => c.id === id); assert.ok(citation);
    assert.ok(verifiedEvidence(report, citation).length);
  }
});
