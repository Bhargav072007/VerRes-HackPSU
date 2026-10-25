import { test, expect } from "@playwright/test";
import paper3 from "./fixtures/prod/paper3-job.json";
import paper2 from "./fixtures/prod/paper2-job.json";

for (const width of [1440, 390]) for (const reducedMotion of ["no-preference", "reduce"] as const) {
  for (const [name, report] of [["paper3", paper3], ["paper2", paper2]] as const) {
    test(`D12 ${name} ${width} ${reducedMotion}: receipts, visible tiles, graph and chrome`, async ({ page }, info) => {
      const errors: string[] = [];
      page.on("pageerror", e => errors.push(e.message));
      page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ reducedMotion });
      await page.route(`**/jobs/${report.job_id}`, route => route.fulfill({ json: report }));
      await page.goto(`/report/${report.job_id}`);
      await expect(page.getByRole("heading", { name: report.paper.title })).toBeVisible();
      await expect(page.getByRole("link", { name: "VerRes home" })).toHaveCount(1);
      await expect(page.locator(".nav-section")).toHaveText("03 · REPORT");
      await expect(page.locator(".polish-nav [aria-current]")).toHaveCount(0);
      await expect(page.getByText("Overstated", { exact: true })).toHaveCount(0);
      const tiles = page.locator(".stat-tile");
      await expect(tiles).toHaveCount(6);
      for (const tile of await tiles.all()) {
        await expect(tile).toBeVisible();
        await expect(tile).toHaveCSS("opacity", "1");
        await expect(tile).toHaveCSS("animation-name", "none");
        await expect(tile.locator("dd")).toHaveAttribute("aria-label", /^\d+ /);
      }
      if (name === "paper2" && reducedMotion === "no-preference") {
        await page.waitForTimeout(8100);
        for (const tile of await tiles.all()) await expect(tile).toHaveCSS("opacity", "1");
      }
      await expect(page.getByLabel(name === "paper3" ? "1 partially supported" : "1 retracted", { exact: true })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: info.outputPath(`${name}-${width}-${reducedMotion}.png`), fullPage: true, animations: "disabled" });
      if (name === "paper3") {
        for (const [id, label, color] of [["c00001", "Supported", "rgb(47, 125, 79)"], ["c00003", "Partially supported", "rgb(183, 121, 31)"]]) {
          const citation = page.locator(`[data-citation-id="${id}"]`);
          await expect(citation).toHaveAttribute("aria-label", new RegExp(`: ${label}\\. Open evidence`));
          await expect(citation.locator("xpath=../preceding-sibling::span[1]")).toHaveCSS("text-decoration-color", color);
          await citation.click();
          await expect(page.getByRole("dialog").locator(".verdict-chip").first()).toHaveText(label);
          await expect(page.getByRole("dialog").locator(".verdict-chip").first()).toHaveCSS("color", color);
          await expect(page.getByRole("dialog").locator("blockquote")).toBeVisible();
          await page.keyboard.press("Escape");
          await expect(page.getByRole("dialog")).toHaveCount(0);
        }
        await expect(page.locator('[data-source-id="b1"]')).toContainText("Partially supported");
        await expect(page.locator('[data-source-id="b3"]')).toContainText("Not found");
        await expect(page.locator('[data-source-id="b4"]')).toContainText("DOI mismatch");
        await page.getByRole("button", { name: "Problems only", exact: true }).click();
        await expect(page.locator('[data-citation-id="c00001"]')).toHaveCount(0);
        await expect(page.locator('[data-citation-id="c00003"]')).toBeVisible();
        await page.getByRole("button", { name: "Needs review", exact: true }).click();
        await expect(page.locator('[data-citation-id="c00003"]')).toHaveCount(0);
        await page.getByRole("button", { name: "All", exact: true }).click();
      } else {
        await expect(page.locator('[data-citation-id="c00001"]')).toHaveAttribute("aria-label", /Retracted/);
        await expect(page.locator('[data-source-id="b0"]')).toContainText("Wakefield");
        await expect(page.locator('[data-source-id="b0"] .verdict-chip').first()).toHaveText("Retracted");
      }
      await page.locator('[aria-label="Filter findings"]').scrollIntoViewIfNeeded();
      await expect(page.locator(".compact-header")).toHaveCSS("opacity", "1");
      await page.getByRole("tablist", { name: "Report views" }).evaluate(node => window.scrollTo({ top: scrollY + node.getBoundingClientRect().top - 140, behavior: "instant" }));
      const nav = await page.locator(".polish-nav").boundingBox();
      const title = await page.locator(".compact-header").boundingBox();
      const tabs = await page.getByRole("tablist", { name: "Report views" }).boundingBox();
      expect(title!.y).toBeGreaterThanOrEqual(nav!.y + nav!.height);
      expect(tabs!.y).toBeGreaterThanOrEqual(title!.y + title!.height);
      expect(tabs!.y).toBeLessThanOrEqual(title!.y + title!.height + 20);
      await page.screenshot({ path: info.outputPath(`sticky-${name}-${width}-${reducedMotion}.png`), animations: "disabled" });
      await page.getByRole("tab", { name: "Claim graph", exact: true }).click();
      const graph = page.getByRole("region", { name: "Claim graph", exact: true });
      if (width === 1440) {
        await expect(page.locator('.react-flow__node[data-id^="source:"]')).toHaveCount(report.paper.references.length);
        const overview = page.locator(".react-flow__minimap");
        await expect(overview.locator(".react-flow__minimap-node")).toHaveCount(report.paper.references.length + report.claim_map.nodes.length);
        await expect(overview).toBeVisible();
        if (name === "paper3") {
          for (const id of ["b3", "b4"]) await expect(page.getByTestId(`rf__node-source:${id}`).locator(".graph-node")).toHaveCSS("border-color", "rgb(180, 35, 24)");
          for (const [id, color] of [["c00001", "rgb(47, 125, 79)"], ["c00003", "rgb(183, 121, 31)"]]) await expect(page.locator(`.react-flow__edge[data-id$=":${id}"] .react-flow__edge-path`)).toHaveCSS("stroke", color);
        }
      } else await expect(page.getByRole("list", { name: "Claim graph list" })).toBeVisible();
      for (const label of name === "paper3" ? ["Not found", "DOI mismatch"] : ["Retracted"]) await expect(graph.getByText(label, { exact: true }).first()).toBeVisible();
      await page.screenshot({ path: info.outputPath(`graph-${name}-${width}-${reducedMotion}.png`), fullPage: true, animations: "disabled" });
      if (width === 1440) {
        await page.locator(".react-flow__minimap-node").evaluateAll(nodes => nodes.forEach(node => node.remove()));
        await expect(page.locator(".react-flow__minimap")).toBeHidden();
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
  }
}

test("landing chrome calls its opening section Overview", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".nav-section")).toHaveText("Overview");
});
