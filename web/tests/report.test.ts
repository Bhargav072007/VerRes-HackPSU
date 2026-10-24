import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { citationVerdict, decodeReport, loadReport, matchesFilter, referenceVerdict, replayReport, reportCounts, verifiedEvidence } from "../lib/report";
const events = readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));
const fixture = () => structuredClone(replayReport(events)!);

test("canonical completed replay has verified quotes, repeated citations and honest counts", () => {
  const report = fixture(), citations = report.paper!.citations!;
  assert.deepEqual(reportCounts(report), [3, 0, 0, 0, 0, 1]);
  assert.deepEqual(citations.map(c => citationVerdict(report, c)), ["SUPPORTED", "NOT_SUPPORTED", "NEEDS_REVIEW", "SUPPORTED"]);
  assert.equal(verifiedEvidence(report, citations[1])[0].quote, "children were not enrolled.");
  assert.equal(matchesFilter(["SUPPORTED"], "Problems only"), false);
  assert.equal(matchesFilter(["NOT_SUPPORTED"], "Problems only"), true);
  assert.equal(matchesFilter(["NEEDS_REVIEW"], "Needs review"), true);
  assert.equal(matchesFilter(["NOT_SUPPORTED"], "Needs review"), false);
  assert.equal(matchesFilter([], "All"), true);
  assert.equal(replayReport([]), null);
});
test("unverifiable quotes, incomplete sources, missing checks and future labels need review", () => {
  for (const mutate of [
    (r: ReturnType<typeof fixture>) => { r.sources![0].passages![0].text = "Different source."; },
    (r: ReturnType<typeof fixture>) => { r.sources![0].status = "CHECK_INCOMPLETE"; },
    (r: ReturnType<typeof fixture>) => { r.support![0].evidence = []; r.support![1].evidence = []; },
    (r: ReturnType<typeof fixture>) => { r.retractions = []; },
  ]) {
    const report = fixture(); mutate(report);
    assert.equal(citationVerdict(report, report.paper!.citations![0]), "NEEDS_REVIEW");
  }
  const report = fixture();
  report.existence![0].status = "AMBIGUOUS";
  assert.equal(referenceVerdict(report, "ref-1"), "NEEDS_REVIEW");
  report.existence![0].status = "NOT_FOUND";
  report.existence![1].status = "DOI_MISMATCH";
  report.retractions![2].status = "RETRACTED";
  assert.deepEqual(reportCounts(report).slice(0, 4), [3, 1, 1, 1]);
  assert.equal(citationVerdict(report, report.paper!.citations![2]), "RETRACTED");
  const partial = fixture(); partial.support![0].label = "PARTIALLY_SUPPORTED";
  assert.equal(reportCounts(partial)[4], 1);
  const future = decodeReport({ ...fixture(), support: [{ ...fixture().support![1], label: "FUTURE" }] })!;
  assert.equal(citationVerdict(future, future.paper!.citations![0]), "NEEDS_REVIEW");
});
test("malformed external snapshots never reach the renderer", () => {
  for (const bad of [null, {}, { status: "UNKNOWN" }, { ...fixture(), paper: { sentences: [null] } }, { ...fixture(), support: [null] }, { ...fixture(), sources: [{ reference_id: "x", evidence_level: "toString" }] }, { ...fixture(), existence: [{ reference_id: "x", status: "VERIFIED", receipt_urls: [{}] }] }]) assert.equal(decodeReport(bad), null);
  assert.ok(decodeReport({ status: "CHECK_INCOMPLETE", paper: null }));
});
test("snapshot loading uses GET, preserves completed data and handles unavailable services", async t => {
  t.mock.method(globalThis, "fetch", async (url: string, options: RequestInit) => {
    assert.ok(url.endsWith("/jobs/a%2Fb")); assert.equal(options.cache, "no-store");
    return Response.json(fixture());
  });
  assert.deepEqual(await loadReport("a/b", new AbortController().signal), fixture());
  t.mock.method(globalThis, "fetch", async () => new Response("unavailable", { status: 503 }));
  assert.equal(await loadReport("id", new AbortController().signal), null);
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Network failure"); });
  assert.equal(await loadReport("id", new AbortController().signal), null);
});
test("mock loading replays the canonical completion and handles corrupt fixture data", async t => {
  const previous = process.env.NEXT_PUBLIC_MOCK;
  process.env.NEXT_PUBLIC_MOCK = "1";
  t.after(() => { if (previous === undefined) delete process.env.NEXT_PUBLIC_MOCK; else process.env.NEXT_PUBLIC_MOCK = previous; });
  t.mock.method(globalThis, "fetch", async (url: string) => {
    assert.equal(url, "/fixtures/events/paper1.jsonl");
    return new Response(events.map(e => JSON.stringify(e)).join("\n"));
  });
  assert.deepEqual(await loadReport("mock", new AbortController().signal), fixture());
  t.mock.method(globalThis, "fetch", async () => new Response("bad json"));
  assert.equal(await loadReport("mock", new AbortController().signal), null);
});
