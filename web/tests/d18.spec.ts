import { test, expect, type Page } from "@playwright/test";

const heroAt = (page: Page, p: number) => page.evaluate(p => { const s = document.querySelector<HTMLElement>(".hero-scene")!; scrollTo({ top: s.offsetTop + p * Math.max(0, s.offsetHeight - innerHeight), behavior: "instant" }); }, p);

for (const [width, height] of [[1440, 900], [1280, 800], [1024, 768], [390, 844]]) test(`D18 hero tally never overlaps a reference slot at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height }); await page.goto("/");
  if (width < 900) await page.locator(".hero-tally").scrollIntoViewIfNeeded(); else await heroAt(page, 1);
  await expect(page.locator(".hero-slot[data-filled=true]")).toHaveCount(8);
  await expect.poll(() => page.locator(".hero-tally").evaluate(n => getComputedStyle(n).opacity)).toBe("1");
  const overlaps = await page.evaluate(() => {
    const tally = document.querySelector(".hero-tally")!.getBoundingClientRect();
    return [...document.querySelectorAll(".hero-slot")].filter(slot => { const r = slot.getBoundingClientRect(); return r.left < tally.right && tally.left < r.right && r.top < tally.bottom && tally.top < r.bottom; }).length;
  });
  expect(overlaps).toBe(0);
  if (width >= 900) expect(await page.evaluate(() => document.querySelector(".hero-paper")!.getBoundingClientRect().bottom <= document.querySelector(".hero-stage")!.getBoundingClientRect().bottom)).toBe(true);
});

test("D18 review room replays the recorded sample: every agent ends terminal, then the report opens", async ({ page }) => {
  const { readFileSync } = await import("node:fs");
  const events = readFileSync("../fixtures/demo/paper3.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));
  const done = events.at(-1).payload;
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("**/jobs/room-sample", route => route.fulfill({ json: route.request().url().includes("/report/") ? done : { events, ...done } }));
  await page.route("**/jobs/room-sample/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
  await page.goto("/check/room-sample");
  await expect(page.locator(".agent-card")).toHaveCount(11);
  for (const card of await page.locator(".agent-card").all()) await expect(card).toHaveAttribute("data-status", /^(DONE|FLAGGED|NEEDS_REVIEW)$/);
  await expect(page.locator('.agent-card[data-agent="resolver"]')).toHaveAttribute("data-status", "FLAGGED");
  await expect(page.locator(".room-done")).toContainText("Review complete");
  await expect(page.locator(".room-slots .hero-slot[data-filled=true]")).toHaveCount(5);
  await expect(page.locator(".room-feed")).toContainText("[4] Kowalczyk 2021 Not found in Crossref, OpenAlex, arXiv");
  await expect(page).toHaveURL("/report/room-sample", { timeout: 6000 });
});

test("D18 review room stays put after done if the reader interacts", async ({ page }) => {
  const { readFileSync } = await import("node:fs");
  const events = readFileSync("../fixtures/demo/paper3.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));
  await page.route("**/jobs/room-stay", route => route.fulfill({ json: { events } }));
  await page.route("**/jobs/room-stay/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
  await page.goto("/check/room-stay");
  await expect(page.locator(".room-done")).toBeVisible();
  await page.mouse.move(200, 300); await page.mouse.move(260, 340);
  await page.waitForTimeout(3600);
  await expect(page).toHaveURL("/check/room-stay");
});

for (const [name, url] of [["landing", "/"], ["review room", "/check/axe-sample"], ["report", "/report/sample-paper3"]] as const) test(`D18 dark theme has no axe violations: ${name}`, async ({ page }) => {
  const { default: AxeBuilder } = await import("@axe-core/playwright");
  const { readFileSync } = await import("node:fs");
  const events = readFileSync("../fixtures/demo/paper3.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));
  await page.route("**/jobs/axe-sample", route => route.fulfill({ json: { events } }));
  await page.route("**/jobs/axe-sample/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => { try { localStorage.setItem("verres-theme", "dark"); } catch { /* storage optional */ } });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(url); await page.evaluate(() => document.fonts.ready);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  if (name === "review room") { await expect(page.locator(".room-done")).toBeVisible(); await page.mouse.move(10, 10); }
  if (name === "report") await expect(page.getByRole("article", { name: "Paper text" })).toBeVisible();
  const { violations } = await new AxeBuilder({ page }).analyze();
  expect(violations.map(v => `${v.id}: ${v.nodes.slice(0, 3).map(n => n.target.join(" ")).join(" | ")}`)).toEqual([]);
});

for (const theme of ["light", "dark"] as const) test(`D18 ${theme} snapshots: hero at p=1 and the report`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(t => { try { localStorage.setItem("verres-theme", t); } catch { /* storage optional */ } }, theme);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/"); await page.evaluate(() => document.fonts.ready);
  await heroAt(page, 1);
  await expect(page.locator(".hero-paper")).toHaveScreenshot(`hero-paper-${theme}.png`, { animations: "disabled", maxDiffPixelRatio: .01 });
  await page.goto("/report/sample-paper3"); await expect(page.getByRole("article", { name: "Paper text" })).toBeVisible();
  await expect(page.locator(".summary-table")).toHaveScreenshot(`report-summary-${theme}.png`, { animations: "disabled", maxDiffPixelRatio: .01 });
});
