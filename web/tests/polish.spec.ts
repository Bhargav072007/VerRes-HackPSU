import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { replayReport } from "../lib/report";

const events = readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));
const report = replayReport(events)!;

for (const width of [1440, 390]) {
  for (const reducedMotion of ["no-preference", "reduce"] as const) {
    test(`polish at ${width}px with ${reducedMotion} motion`, async ({ page }, info) => {
      const errors: string[] = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ reducedMotion });
      await page.route("**/jobs/polish-live", route => route.fulfill({ json: { events: events.slice(0, 31) } }));
      await page.route("**/jobs/polish-live/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
      await page.route("**/jobs/polish-report", route => route.fulfill({ json: report }));
      for (const [name, url] of [["landing", "/"], ["live", "/check/polish-live"], ["report", "/report/polish-report"]]) {
        await page.goto(url);
        await page.evaluate(() => document.fonts.ready);
        await expect(page).toHaveTitle("VerRes — proof, not vibes");
        await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", "VerRes — proof, not vibes");
        if (name === "live") {
          await expect(page.locator('[data-chip="Verified"]')).toHaveCount(3);
          await expect(page.getByText("Happening now")).toBeVisible();
          if (reducedMotion === "reduce") await expect(page.locator("[data-reference-id]").first()).toHaveCSS("transform", "none");
        }
        if (name === "report") await expect(page.locator("[data-citation-id]")).toHaveCount(4);
        await page.waitForTimeout(400); // Wait for the maximum allowed reveal/counter duration.
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath(`${name}-${width}-${reducedMotion}.png`), fullPage: true, animations: "disabled" });
        if (name === "landing") {
          await expect(page.getByLabel("arXiv ID or DOI", { exact: true })).toHaveCSS("border-color", "rgb(156, 155, 152)");
          await page.keyboard.press("Tab");
          await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
          await expect(page.getByRole("link", { name: "Skip to content" })).toHaveCSS("outline-style", "solid");
        }
        if (name === "report") {
          await page.setViewportSize({ width, height: 600 });
          const tabs = page.getByRole("tablist", { name: "Report views" });
          await tabs.evaluate(node => window.scrollTo({ top: window.scrollY + node.getBoundingClientRect().top + 50, behavior: "instant" }));
          await expect.poll(() => tabs.evaluate(node => Math.round(node.getBoundingClientRect().top))).toBe(0);
          for (const tab of await page.getByRole("tab").all()) {
            await tab.click();
            await expect(page.getByRole("tabpanel")).toBeVisible();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
          }
        }
      }
      expect(errors).toEqual([]);
    });
  }
}
