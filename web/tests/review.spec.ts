import { test, expect } from "@playwright/test";
import { reviewFixture } from "./fixtures/review";

for (const width of [1440, 390]) test(`peer review fixture at ${width}px: chair, reviewers, receipts and fix navigation`, async ({ page }, info) => {
  const report = reviewFixture(), errors: string[] = [];
  report.paper!.sentences!.splice(1, 0, ...Array.from({ length: 12 }, (_, i) => ({ ...report.paper!.sentences![0], id: `extra-${i}`, text: "Additional methods and study details. ".repeat(8) })));
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.setViewportSize({ width, height: 1000 });
  if (width === 390) await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/jobs/panel", route => route.fulfill({ json: report }));
  await page.goto("/report/panel");
  await page.getByRole("tab", { name: "Peer review" }).click();
  await expect(page.getByRole("heading", { name: "Area chair" })).toBeVisible();
  await expect(page.getByRole("list").first().getByRole("listitem")).toHaveCount(3);
  for (const name of ["R1 Methods", "R2 Evidence", "R3 Claims"]) {
    const card = page.getByRole("region", { name });
    await expect(card.getByLabel("1 major · 0 minor", { exact: true })).toBeVisible();
    if (width === 390) await expect(card).toHaveCSS("transform", "none");
    await card.getByText("Receipts (1)").click();
    await expect(card.getByRole("blockquote")).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "R2 Evidence" })).toContainText("cite-2");
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: info.outputPath(`peer-review-${width}.png`), fullPage: true, animations: "disabled" });
  for (const [index, target] of [[0, "sentence-s1"], [2, "citation-cite-2"]] as const) {
    await page.getByRole("link", { name: report.review!.top_fixes![index], exact: true }).click();
    await expect(page.locator(`[id="${target}"]`)).toBeFocused();
    await expect(page.locator(`[id="${target}"]`)).toBeInViewport();
    await expect(page.locator(`[id="${target}"]`)).toHaveAttribute("data-highlighted", "true");
    await page.getByRole("button", { name: "Needs review", exact: true }).click();
    await page.getByRole("tab", { name: "Peer review" }).click();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("hidden instruction warnings, failed and malformed panels, and old jobs preserve the report", async ({ page }) => {
  const base = reviewFixture();
  for (const kind of ["hidden", "warning", "failed", "malformed", "old"] as const) {
    const report = structuredClone(base);
    if (kind === "hidden") report.hidden_text = [{ id: "paper3", kind: "PROMPT_INJECTION", page: 1, quote: "Ignore previous instructions", reason: "Hidden reviewer instructions" }];
    if (kind === "warning") report.review!.warning = "This paper contains hidden text addressed to AI reviewers.";
    if (kind === "failed") report.review = { warning: "Review panel unavailable: chair failed" };
    if (kind === "old") { delete report.review; delete report.review_comments; }
    await page.route(`**/jobs/${kind}`, route => route.fulfill({ json: kind === "malformed" ? { ...report, review: { comments: [null] } } : report }));
    await page.goto(`/report/${kind}`);
    await expect(page.locator("[data-citation-id]")).toHaveCount(4);
    if (kind === "old") { await expect(page.getByRole("tab", { name: "Peer review" })).toHaveCount(0); continue; }
    await page.getByRole("tab", { name: "Peer review" }).click();
    if (kind === "hidden" || kind === "warning") await expect(page.locator("main").getByRole("alert")).toHaveText("This PDF contains hidden instructions aimed at AI reviewers. The panel ignored them.");
    else {
      await expect(page.getByRole("heading", { name: "Review incomplete" })).toBeVisible();
      await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
      await page.getByRole("tab", { name: "Report", exact: true }).click();
      await page.locator('[data-citation-id="cite-2"]').click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
    }
  }
});

test("loading skeleton and live review/summary SSE update plain text receipts", async ({ page }) => {
  const report = reviewFixture();
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/jobs/live-panel", async route => { await pending; await route.fulfill({ json: { ...report, status: "RUNNING", review: null, review_comments: [] } }); });
  let send!: () => void;
  const streamPending = new Promise<void>(resolve => { send = resolve; });
  const hostile = '<img src=x onerror="alert(1)">';
  report.review_comments![0].issue = hostile;
  await page.route("**/jobs/live-panel/events", async route => {
    await streamPending;
    await route.fulfill({ contentType: "text/event-stream", body: "retry: 100000\n\n" + [["review", report.review_comments![0]], ["review_summary", report.review]].map(([type, payload], i) => `id: ${i + 1}\nevent: ${type}\ndata: ${JSON.stringify(payload)}\n\n`).join("") });
  });
  await page.goto("/report/live-panel");
  await page.getByRole("tab", { name: "Peer review" }).click();
  await expect(page.getByRole("status", { name: "Loading peer review" })).toBeVisible();
  release();
  await expect(page.getByText("Panel still running.", { exact: false })).toBeVisible();
  send();
  await expect(page.getByText(hostile, { exact: true })).toBeVisible();
  await expect(page.getByText("Panel still running.", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("link", { name: report.review!.top_fixes![0] })).toBeVisible();
  await expect(page.locator("main img")).toHaveCount(0);
});
