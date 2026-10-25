import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { createServer, type ServerResponse } from "node:http";
const journal = (name: string) => readFileSync(`../fixtures/demo/${name}.jsonl`, "utf8").trim().split("\n").map(line => JSON.parse(line));
const frame = (e: ReturnType<typeof journal>[number]) => `id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e.payload)}\n\n`;
declare global { interface Window { liveCLS: number; liveShifts: unknown[] } }

for (const width of [1440, 390]) for (const reducedMotion of ["no-preference", "reduce"] as const) test(`D11 recorded SSE at ${width}px ${reducedMotion}`, async ({ page }, info) => {
  const events = journal("paper3"), errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.setViewportSize({ width, height: 1000 });
  await page.emulateMedia({ reducedMotion });
  await page.addInitScript(() => {
    window.liveCLS = 0; window.liveShifts = [];
    new PerformanceObserver(list => { for (const entry of list.getEntries()) {
      const shift = entry as PerformanceEntry & { value: number; hadRecentInput: boolean };
      if (!shift.hadRecentInput) { window.liveCLS += shift.value; window.liveShifts.push(JSON.parse(JSON.stringify(entry))); }
    } }).observe({ type: "layout-shift", buffered: true });
  });
  let response: ServerResponse | undefined;
  const server = createServer((_, res) => { response = res; res.writeHead(200, { "Content-Type": "text/event-stream", "Access-Control-Allow-Origin": "*" }); res.write(": connected\n\n"); });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Fixture stream unavailable");
  await page.route("**/jobs/d11", route => route.fulfill({ json: { events: [] } }));
  await page.route("**/jobs/d11/events", route => route.continue({ url: `http://127.0.0.1:${address.port}/events` }));
  try {
    await page.goto("/check/d11");
    await expect(page.getByText("No findings yet.")).toBeVisible();
    await expect(page.locator("[data-dot]")).toHaveCount(0);
    await expect.poll(() => !!response).toBe(true);
    for (const event of events.filter(e => e.type !== "done")) {
      response!.write(frame(event));
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    await expect(page.locator("[data-finding]")).toHaveCount(3);
    await expect(page.locator("[data-finding]").first()).toContainText("DOI mismatch");
    await expect(page.locator('[data-finding="existence:b3"]')).toContainText("Reference [4] was not found in Crossref, OpenAlex or arXiv.");
    await expect(page.locator('[data-finding="hidden_text:hidden-00001"]')).toContainText("Hidden text on page 1 needs review.");
    await expect(page.getByRole("status").first()).toHaveAttribute("aria-label", "5 / 5 references checked");
    await expect(page.getByLabel("3 verified quotes", { exact: true })).toBeVisible();
    await expect(page.locator("[data-dot]")).toHaveCount(5);
    await expect(page.getByRole("link", { name: "View receipt" })).toHaveCount(0);
    await expect(page.getByLabel("Live claim graph", { exact: true })).toBeVisible({ visible: width === 1440 });
    const dot = page.locator("[data-dot]").first();
    await dot.scrollIntoViewIfNeeded();
    const box = (await dot.boundingBox())!;
    await page.mouse.move(box.x + 12, box.y + 7);
    await expect.poll(() => dot.evaluate(n => getComputedStyle(n).transform)).toMatch(reducedMotion === "reduce" ? /^none$/ : /^matrix/);
    if (reducedMotion === "no-preference") expect(await dot.evaluate(n => { const m = new DOMMatrix(getComputedStyle(n).transform); return Math.hypot(m.m41, m.m42); })).toBeLessThanOrEqual(4);
    if (reducedMotion === "reduce") expect(await page.locator(".live-check").evaluate(n => n.getAnimations({ subtree: true }).filter(a => a.playState === "running").length)).toBe(0);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: info.outputPath(`live-${width}-${reducedMotion}.png`), fullPage: true });
    const cls = await page.evaluate(() => ({ cls: window.liveCLS, shifts: window.liveShifts }));
    writeFileSync(info.outputPath("layout-shifts.json"), JSON.stringify(cls));
    expect(cls.cls).toBeLessThan(.05);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    response!.write(frame(events.find(e => e.type === "done")!));
    await expect(page.locator('[data-finding="existence:b3"] a')).toHaveAttribute("href", "/report/d11?flag=c00005");
    await expect(page.locator('[data-finding="hidden_text:hidden-00001"] a')).toHaveAttribute("href", "/report/d11#hidden-1-0");
    await page.waitForTimeout(400); // Include completion layout before the existing report redirect.
    const completedCLS = await page.evaluate(() => window.liveCLS);
    writeFileSync(info.outputPath("completion-cls.json"), JSON.stringify({ cls: completedCLS }));
    expect(completedCLS).toBeLessThan(.05);
    expect(errors).toEqual([]);
  } finally { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); }
});

test("D11 Wakefield retraction, collapsed older findings and in-app static motion", async ({ page }) => {
  const events = journal("paper2").filter(e => e.type !== "done");
  await page.route("**/jobs/wakefield", route => route.fulfill({ json: { events } }));
  await page.route("**/jobs/wakefield/events", route => route.fulfill({ contentType: "text/event-stream", body: ": waiting\n\n" }));
  await page.goto("/check/wakefield");
  await expect(page.locator('[data-finding="retraction:b0"]')).toContainText("Reference [1] has been retracted.");
  const hidden = journal("paper3").find(e => e.type === "hidden_text")!;
  for (let i = 0; i < 6; i++) events.push({ ...hidden, seq: 100 + i, payload: { ...hidden.payload, id: `test-hidden-${i}` } });
  await page.reload();
  await expect(page.locator("[data-finding]")).toHaveCount(5);
  await expect(page.getByText("+2 more", { exact: true })).toBeVisible();
  await page.getByText("+2 more", { exact: true }).click();
  await expect(page.locator(".older-findings")).toContainText("Reference [1] has been retracted.");
  await page.evaluate(() => { document.documentElement.dataset.a11yMotion = "reduce"; });
  await expect(page.locator(".reference-field ul")).toHaveAttribute("data-static", "true");
  await expect(page.locator("[data-dot]").first()).toHaveCSS("transform", "none");
});
