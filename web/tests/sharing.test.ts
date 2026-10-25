import assert from "node:assert/strict";
import { test } from "node:test";
import { createShare, loadSharedReport, reportUrl } from "../lib/sharing";
import { reviewFixture } from "./fixtures/review";

test("sharing encodes identifiers and rejects unsafe or malformed share responses", async t => {
  assert.ok(reportUrl("a/b", true).endsWith("/shares/a%2Fb"));
  for (const value of [null, { url: "javascript:alert(1)" }, { url: "https://user:pass@example.com", token: "t", expires_at: "2026-11-24" }, { url: "https://example.com", token: 5, expires_at: "invalid" }]) {
    t.mock.method(globalThis, "fetch", async () => Response.json(value));
    assert.ok((await createShare("id")).error);
  }
});
test("shared loading handles public reports, expired links, bad data and network errors", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ ...reviewFixture(), shared: true }));
  assert.equal((await loadSharedReport("token", new AbortController().signal)).report?.paper?.title, reviewFixture().paper?.title);
  t.mock.method(globalThis, "fetch", async () => new Response("", { status: 410 }));
  assert.deepEqual(await loadSharedReport("token", new AbortController().signal), { report: null, expired: true });
  t.mock.method(globalThis, "fetch", async () => Response.json({ paper: { sentences: [null] } }));
  assert.equal((await loadSharedReport("token", new AbortController().signal)).report, null);
  t.mock.method(globalThis, "fetch", async () => { throw new Error("Offline"); });
  assert.deepEqual(await loadSharedReport("token", new AbortController().signal), { report: null, expired: false });
});
