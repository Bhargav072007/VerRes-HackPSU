import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
const events = readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map((line, index) => ({ ...JSON.parse(line), at: index * 100 }));
const mock = process.env.NEXT_PUBLIC_MOCK === "1";
const sse = (list: typeof events) => "retry: 100\n\n" + list.map(e => `id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e.payload)}\n\n`).join("");

test.describe("live transport", () => {
  test.skip(mock, "Uses the real transport build");
  test("snapshot first, native Last-Event-ID replay, stable rows and done redirect", async ({ page }, info) => {
    const order: string[] = [], cursors: (string | undefined)[] = [], errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/jobs/browser-run", route => { order.push("snapshot"); return route.fulfill({ json: { events: events.slice(0, 6) } }); });
    // Observe headers on the wire: Chromium adds Last-Event-ID after route interception.
    const server = createServer((request, response) => {
      response.setHeader("Access-Control-Allow-Origin", "*");
      response.setHeader("Access-Control-Allow-Headers", "Last-Event-ID");
      if (request.method === "OPTIONS") { response.end(); return; }
      order.push("stream"); cursors.push(request.headers["last-event-id"] as string | undefined);
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      response.end(sse(cursors.length === 1 ? events.slice(0, 10) : events));
    });
    await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("Fixture server failed to start");
    await page.route("**/jobs/browser-run/events", route => route.continue({ url: `http://127.0.0.1:${address.port}/events` }));
    try {
      await page.goto("/check/browser-run");
      await expect(page.locator("[data-reference-id]")).toHaveCount(3);
      await page.locator('[data-reference-id="ref-1"]').evaluate(node => { node.setAttribute("data-original", "yes"); });
      await expect(page.getByRole("link", { name: "View report" })).toBeVisible();
      writeFileSync(info.outputPath("reconnect-requests.json"), JSON.stringify({ order, cursors }));
      expect(order.slice(0, 2)).toEqual(["snapshot", "stream"]);
      expect(cursors.slice(0, 2)).toEqual([undefined, String(events[9].seq)]);
      await expect(page.locator('[data-reference-id="ref-1"]')).toHaveAttribute("data-original", "yes");
      await expect(page.locator('[data-reference-id="ref-2"]')).toContainText("Fixture trial 2");
      await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3);
      await expect(page.getByRole("status").first()).toHaveAttribute("aria-label", "3 / 3 references checked");
      await page.screenshot({ path: info.outputPath("live-complete.png") });
      await expect(page).toHaveURL(/\/report\/browser-run$/);
      expect(errors).toEqual([]);
    } finally { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); }
  });
  test("two failed native reconnects switch to snapshot polling every two seconds", async ({ page }) => {
    let snapshots = 0, streams = 0;
    const times: number[] = [];
    await page.route("**/jobs/poll-run", route => {
      times.push(Date.now()); snapshots++;
      return route.fulfill({ json: { events: snapshots === 1 ? events.slice(0, 10) : snapshots === 2 ? events.slice(0, 31) : events } });
    });
    await page.route("**/jobs/poll-run/events", route => { streams++; return route.fulfill({ contentType: "text/event-stream", body: "retry: 100\n\n" }); });
    await page.goto("/check/poll-run");
    await expect(page.getByText("Live connection interrupted. Checking snapshots every 2 seconds.")).toBeVisible();
    await expect(page.getByRole("link", { name: "View report" })).toBeVisible({ timeout: 10000 });
    expect(streams).toBe(3);
    expect(snapshots).toBe(3);
    expect(times[2] - times[1]).toBeGreaterThanOrEqual(1900);
  });
  test("refresh restores journal receipts even if the connection is unavailable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.route("**/jobs/refresh-run", route => route.fulfill({ json: { events: events.slice(0, 31) } }));
    await page.route("**/jobs/refresh-run/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 10000\n\n" }));
    await page.goto("/check/refresh-run");
    await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3);
    await page.reload();
    await expect(page.locator("[data-reference-id]")).toHaveCount(3);
    await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3);
    await expect(page.locator('[data-reference-id="ref-2"]')).toContainText("Fixture trial 2");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
  test("real development API stream and snapshot survive refresh during replay", async ({ page, request }, info) => {
    test.skip(process.env.LIVE_API !== "1", "Opt in with LIVE_API=1 and ENV=dev API");
    let id = process.env.LIVE_JOB_ID;
    if (!id) {
      const response = await request.post("http://localhost:8000/dev/fake-job");
      expect(response.status()).toBe(202);
      id = (await response.json()).job_id;
    }
    // Reuse a completed dev job without consuming quota: start from an earlier
    // real snapshot journal, then let the actual SSE endpoint replay its receipts.
    if (process.env.LIVE_JOB_ID) await page.route(`**/jobs/${id}`, async route => {
      const response = await route.fetch();
      const data = await response.json();
      await route.fulfill({ response, json: { ...data, events: data.events.slice(0, 6) } });
    }, { times: 1 });
    const received: string[] = [];
    page.on("response", response => { if (response.url().includes(`/jobs/${id}`)) received.push(response.url()); });
    await page.goto(`/check/${id}`);
    await expect(page.locator('[data-reference-id="ref-1"]')).toBeVisible();
    await expect(page.locator('[data-chip="Verified"]')).toHaveCount(1);
    await page.reload();
    await expect(page.locator('[data-reference-id="ref-1"]')).toBeVisible();
    await expect(page.getByRole("link", { name: "View report" })).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-chip="Verified"]')).toHaveCount(1);
    await page.screenshot({ path: info.outputPath("real-api.png") });
    await expect(page).toHaveURL(new RegExp(`/report/${id}$`));
    expect(received.some(url => url.endsWith("/events"))).toBe(true);
  });
});

test("mock plays a complete run, restores its clock on refresh, and stays within a frame budget", async ({ page }, info) => {
  test.skip(!mock, "Build with NEXT_PUBLIC_MOCK=1");
  await page.goto(`/check/mock-${Date.now()}`);
  await expect(page.locator("[data-reference-id]")).toHaveCount(3);
  await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3, { timeout: 10000 });
  await page.reload();
  await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3);
  const frames = await page.evaluate(() => new Promise<number[]>(resolve => {
    const durations: number[] = []; let last = performance.now(); const start = last;
    const tick = (now: number) => { durations.push(now - last); last = now; if (now - start < 3000) requestAnimationFrame(tick); else resolve(durations.slice(1)); }; requestAnimationFrame(tick);
  }));
  const sorted = frames.toSorted((a, b) => a - b);
  const metrics = { frames: frames.length, medianMs: sorted[Math.floor(sorted.length / 2)], p95Ms: sorted[Math.floor(sorted.length * .95)] };
  writeFileSync(info.outputPath("frame-timing.json"), JSON.stringify(metrics));
  await info.attach("frame-timing", { body: JSON.stringify(metrics), contentType: "application/json" });
  expect(metrics.medianMs).toBeLessThan(20);
  expect(metrics.p95Ms).toBeLessThan(34);
  await expect(page.getByRole("link", { name: "View report" })).toBeVisible({ timeout: 22000 });
  await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3);
  await page.screenshot({ path: info.outputPath("mock-complete.png") });
  await expect(page).toHaveURL(/\/report\/mock-/);
});
