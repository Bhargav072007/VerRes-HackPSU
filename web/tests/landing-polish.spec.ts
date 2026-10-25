import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const journal = readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));

for (const width of [1440, 390]) for (const reducedMotion of ["no-preference", "reduce"] as const) {
  test(`D9 landing and live screenshots ${width} ${reducedMotion}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion });
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator(".hero-scene")).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Read your paper like Reviewer 2 would." })).toBeVisible();
    await expect(page).toHaveScreenshot(`landing-${width}-${reducedMotion}.png`, { animations: "disabled", maxDiffPixelRatio: .01 });
    if (width === 390) {
      await page.getByLabel("Navigation menu").click();
      await page.getByRole("navigation", { name: "Mobile navigation" }).getByRole("link", { name: "Method" }).click();
      await expect(page.locator(".polish-menu")).not.toHaveAttribute("open");
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    }
    await expect(page.locator(".polish-nav")).toHaveCSS("position", "relative");
    await page.locator("#submit").scrollIntoViewIfNeeded();
    await expect(page.locator(".upload-card")).toBeVisible();
    await expect(page.getByRole("button", { name: "Planted problems", exact: true })).toBeVisible();
    await page.getByLabel("arXiv ID or DOI", { exact: true }).fill("invalid");
    await page.getByLabel("arXiv ID or DOI", { exact: true }).blur();
    await expect(page.locator("#submission-error")).toContainText("Enter an arXiv ID or DOI");
    await page.getByLabel("arXiv ID or DOI", { exact: true }).fill("");
    await page.locator("#honesty").scrollIntoViewIfNeeded();
    await expect(page.locator(".limitations")).toBeVisible();
    await expect(page.locator(".limitations")).toContainText("Needs review");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.route("**/jobs/d9-polish", route => route.fulfill({ json: { events: journal.slice(0, 31) } }));
    await page.route("**/jobs/d9-polish/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
    await page.goto("/check/d9-polish");
    await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3);
    await expect(page.locator(".stage-rail li")).toHaveCount(6);
    await expect(page.locator(".stage-rail [aria-current=step]")).toContainText("Sources");
    await expect(page.locator(".stage-progress")).toContainText("Stage 4 of 6");
    await expect(page.getByText("ETA unavailable")).toHaveCount(0);
    await expect(page).toHaveScreenshot(`live-${width}-${reducedMotion}.png`, { animations: "disabled", maxDiffPixelRatio: .01 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("D9 flags uncertain results, preserves receipts and honors the in-app motion override", async ({ page }) => {
  const events = structuredClone(journal.slice(0, 18));
  events.find(event => event.type === "existence").payload.status = "NOT_FOUND";
  await page.route("**/jobs/d9-flags", route => route.fulfill({ json: { events } }));
  await page.route("**/jobs/d9-flags/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
  await page.goto("/check/d9-flags");
  await expect(page.locator(".stage-panel")).toContainText("FLAGGED");
  await page.locator("[data-reference-id=ref-1] summary").click();
  await expect(page.locator("[data-reference-id=ref-1]")).toContainText("Not found in Crossref, OpenAlex or arXiv");
  await page.goto("/");
  await page.evaluate(() => { document.documentElement.dataset.a11yMotion = "reduce"; });
  await expect(page.locator(".hero-paper")).toHaveCSS("transform", /^(none|matrix\(([\d.]+), 0, 0, \2, 0, 0\))$/);

});

test("D9 upload connects the shared card to the live header", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/jobs", route => route.fulfill({ status: 202, json: { job_id: "d9-morph" } }));
  await page.route("**/jobs/d9-morph", route => route.fulfill({ json: { events: journal.slice(0, 31) } }));
  await page.route("**/jobs/d9-morph/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
  await page.goto("/");
  await page.getByLabel("arXiv ID or DOI", { exact: true }).fill("2401.12345");
  await page.getByRole("button", { name: "Review my paper" }).click();
  await expect(page).toHaveURL("/check/d9-morph");
  await expect(page.getByRole("heading", { name: "Following the evidence." })).toBeVisible();
  await expect(page.locator("[data-reference-id]")).toHaveCount(3);
  expect(errors).toEqual([]);
});
