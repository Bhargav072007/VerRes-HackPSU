import assert from "node:assert/strict";
import { test } from "node:test";
import fixtures from "../fixtures/submission.json";
import { createJob, getHealth, parseIdentifier, validatePdf } from "../lib/api";
import { cn } from "../lib/utils";

test("identifier detection matches the A2 request shape", () => {
  for (const [value, expected] of fixtures.identifiers)
    assert.deepEqual(parseIdentifier(value as string), expected);
  for (const value of fixtures.invalidIdentifiers)
    assert.equal(parseIdentifier(value), null);
  assert.deepEqual(parseIdentifier("  2401.12345  "), {
    arxiv_id: "2401.12345",
  });
});
test("PDF validation handles type, empty files and the 25MB boundary", () => {
  const pdf = {
    name: "paper.pdf",
    type: "application/pdf",
    size: 25 * 1024 * 1024,
  };
  assert.equal(validatePdf(pdf), null);
  assert.equal(validatePdf({ ...pdf, type: "" }), null);
  assert.match(validatePdf({ ...pdf, size: pdf.size + 1 })!, /exceeds 25MB/);
  assert.match(validatePdf({ ...pdf, size: 0 })!, /empty/);
  assert.match(validatePdf({ ...pdf, name: "paper.txt" })!, /choose a PDF/);
  assert.match(validatePdf({ ...pdf, type: "image/png" })!, /choose a PDF/);
});
test("API submission sends real multipart or JSON and handles external failures", async (t) => {
  const requests: RequestInit[] = [];
  t.mock.method(
    globalThis,
    "fetch",
    async (_url: unknown, options: RequestInit) => {
      requests.push(options);
      return Response.json({ job_id: "paper-1" }, { status: 202 });
    },
  );
  assert.deepEqual(await createJob({ identifier: "2401.12345" }), {
    ok: true,
    job_id: "paper-1",
  });
  assert.equal(requests[0].body, '{"arxiv_id":"2401.12345"}');
  assert.deepEqual(requests[0].headers, { "Content-Type": "application/json" });
  await createJob({ identifier: "10.1000/xyz" });
  assert.equal(requests[1].body, '{"doi":"10.1000/xyz"}');
  await createJob({
    file: new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }),
  });
  assert.ok(requests[2].body instanceof FormData);
  assert.equal((requests[2].body.get("file") as File).name, "paper.pdf");
  assert.equal((await createJob({ identifier: "invalid" })).ok, false);
  assert.equal(
    (await createJob({ file: new File(["bad"], "paper.txt") })).ok,
    false,
  );
  assert.equal(requests.length, 3);
  for (const code of fixtures.apiErrors) {
    t.mock.method(globalThis, "fetch", async () =>
      Response.json(
        { code, message: "Please try another paper." },
        { status: 422 },
      ),
    );
    assert.deepEqual(await createJob({ identifier: "2401.12345" }), {
      ok: false,
      error: { code, message: "Please try another paper." },
    });
  }
  for (const response of [
    new Response("Not found", { status: 404 }),
    Response.json({ job_id: "" }, { status: 202 }),
    new Response("Bad gateway", { status: 502 }),
    Response.json({ code: 42, message: {} }, { status: 422 }),
  ]) {
    t.mock.method(globalThis, "fetch", async () => response);
    const result = await createJob({ identifier: "2401.12345" });
    assert.equal(result.ok, false);
    if (!result.ok)
      assert.ok(
        result.error.message && !result.error.message.includes("Bad gateway"),
      );
  }
  t.mock.method(globalThis, "fetch", async () => {
    throw new TypeError("Network failed");
  });
  const result = await createJob({ identifier: "2401.12345" });
  assert.equal(result.ok, false);
  if (!result.ok) assert.equal(result.error.code, "UNAVAILABLE");
});
test("typed health client returns CHECK_INCOMPLETE for invalid external data", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    Response.json(fixtures.health),
  );
  assert.deepEqual(await getHealth(), fixtures.health);
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ status: "unknown" }),
  );
  assert.equal((await getHealth()).status, "CHECK_INCOMPLETE");
  t.mock.method(globalThis, "fetch", async () => {
    throw new TypeError("Offline");
  });
  assert.equal((await getHealth()).status, "CHECK_INCOMPLETE");
});
test("UI class utility resolves conflicting Tailwind classes", () => {
  assert.equal(cn("p-2", false, "p-4"), "p-4");
});
