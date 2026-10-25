import { test, expect } from "@playwright/test";
import { reviewFixture } from "./fixtures/review";

for (const width of [1440, 390]) test(`informational citations do not look like unresolved findings at ${width}px`, async ({ page }) => {
  const report = reviewFixture();
  report.existence!.forEach(row => { row.status = "VERIFIED"; });
  report.retractions!.forEach(row => { row.status = "NONE"; });
  report.support!.forEach((row, i) => { row.label = "NEEDS_REVIEW"; row.evidence = []; row.reason = row.needs_review_reason = i % 2 ? "Method reference: this citation identifies a method or tool, not a specific finding." : "Background citation: no specific factual finding is attributed to this source."; });
  await page.route("**/jobs/outcomes", route => route.fulfill({ json: report }));
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/report/outcomes");
  await expect(page.locator(".margin-note").getByText("Background citation", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".margin-note").getByText("Method reference", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Checks summary" })).toContainText("NOT APPLICABLE");
  await expect(page.getByLabel("0 unresolved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Unresolved", exact: true }).click();
  await expect(page.locator("[data-citation-id]")).toHaveCount(0);
  await page.getByRole("button", { name: "Problems only", exact: true }).click();
  await expect(page.locator("[data-citation-id]")).toHaveCount(0);
});
