import { test, expect } from "@playwright/test";
import { claimGraphFixture } from "./fixtures/claim-graph";
import { reviewFixture } from "./fixtures/review";
import { emptyProvenance } from "./fixtures/provenance";

for (const width of [1440, 390]) test(`claim graph at ${width}px: receipts, legend, evidence navigation and fallback`, async ({ page }, info) => {
  const errors: string[] = [], report = claimGraphFixture();
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.setViewportSize({ width, height: 1000 });
  await page.route("**/jobs/graph", route => route.fulfill({ json: report }));
  await page.goto("/report/graph");
  await page.getByRole("tab", { name: "Claim graph" }).click();
  const legend = page.getByLabel("Graph legend");
  await expect(legend).toBeVisible();
  for (const label of ["Supported", "Partially supported", "Not supported", "Contradicted", "Needs review"]) await expect(legend.getByText(label, { exact: true })).toBeVisible();
  if (width < 640) {
    await expect(page.getByRole("list", { name: "Claim graph list" })).toBeVisible();
    await expect(page.getByTestId("claim-graph-canvas")).toHaveCount(0);
  } else {
    await page.getByTestId("claim-graph-canvas").scrollIntoViewIfNeeded();
    await expect(page.locator(".react-flow__node")).toHaveCount(5);
    await expect(page.locator(".react-flow__edge")).toHaveCount(4);
    await expect(page.getByRole("button", { name: "Zoom In", exact: true })).toBeVisible();
    const node = page.getByTestId("rf__node-claim:claim-1");
    await node.focus(); await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toContainText("Treatment improved outcomes in adults.");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: info.outputPath(`claim-graph-${width}.png`), fullPage: true });
  if (width < 640) await page.getByRole("list", { name: "Claim graph list" }).getByRole("button", { name: /Fixture trial 2/ }).click();
  else {
    const point = await page.getByTestId("rf__edge-citation:claim-2:cite-2").locator(".react-flow__edge-path").evaluate(n => {
      const path = n as SVGPathElement, point = path.getPointAtLength(path.getTotalLength() / 2).matrixTransform(path.getScreenCTM()!);
      return { x: point.x, y: point.y };
    });
    await page.mouse.click(point.x, point.y);
  }
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "Claim receipt", exact: true })).toBeVisible();
  await expect(sheet).toContainText("Treatment benefits extend to children.");
  await expect(sheet).toContainText("Not supported");
  await expect(sheet.getByRole("blockquote")).toContainText("children were not enrolled.");
  await expect(sheet).toHaveCSS("transform", "none");
  await page.screenshot({ path: info.outputPath(`claim-receipt-${width}.png`), animations: "disabled" });
  await sheet.getByRole("button", { name: "Open in evidence panel" }).click();
  await expect(page.getByRole("tab", { name: "Report", exact: true, includeHidden: true })).toHaveAttribute("data-state", "active");
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Evidence receipt" })).toBeVisible();
  await expect(page).toHaveURL(/flag=cite-2/);
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-citation-id="cite-2"]')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

for (const width of [1440, 390]) test(`missing, empty, incomplete and hostile maps at ${width}px with reduced motion`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const report = claimGraphFixture();
  await page.route("**/jobs/states", route => route.fulfill({ json: report }));
  await page.route("**/jobs/states/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 100000\n\n" }));
  report.claim_map = null;
  await page.goto("/report/states");
  await expect(page.getByRole("heading", { name: report.paper!.title! })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Claim graph" })).toHaveCount(0);
  report.claim_map = { ...emptyProvenance, paper_id: "fixture", nodes: [], edges: [], status: "COMPLETE", needs_review_reason: null };
  await page.reload(); await page.getByRole("tab", { name: "Claim graph" }).click();
  await expect(width < 640 ? page.getByRole("list", { name: "Claim graph list" }) : page.getByTestId("claim-graph-canvas")).toBeVisible();
  report.claim_map = claimGraphFixture().claim_map;
  report.claim_map!.status = "NEEDS_REVIEW"; report.claim_map!.needs_review_reason = "Some claims could not be mapped.";
  report.claim_map!.nodes![0].text = '<img src=x onerror="alert(1)">';
  report.existence![0].status = "DOI_MISMATCH"; report.existence![1].status = "NOT_FOUND"; report.retractions![2].status = "RETRACTED";
  await page.reload(); await page.getByRole("tab", { name: "Claim graph" }).click();
  await expect(page.getByText("Some claims could not be mapped.")).toBeVisible();
  for (const [id, source, label] of [["ref-1", "Trial", "DOI mismatch"], ["ref-2", "Fixture trial 2", "Not found"], ["ref-3", "Fixture trial 3", "Retracted"]]) {
    const node = width < 640 ? page.getByRole("list", { name: "Claim graph list" }).getByRole("button", { name: new RegExp(`^${source} `) }).first() : page.getByTestId(`rf__node-source:${id}`);
    await expect(node).toContainText(label);
    await expect(width < 640 ? node : node.locator("div").first()).toHaveCSS("border-color", "rgb(180, 35, 24)");
  }
  await expect(page.getByText('<img src=x onerror="alert(1)">', { exact: true })).toBeVisible();
  await expect(page.locator("main img")).toHaveCount(0);
  if (width >= 640) await expect(page.locator(".react-flow__edge > g").first()).toHaveCSS("opacity", "1");
  report.status = "RUNNING";
  await page.reload(); await page.getByRole("tab", { name: "Claim graph" }).click();
  report.claim_map = null;
  await expect(page.getByRole("tab", { name: "Claim graph" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Report", exact: true })).toHaveAttribute("data-state", "active");
});

test("graph chunk loading shows an accessible skeleton", async ({ page }) => {
  await page.route("**/jobs/loading-graph", route => route.fulfill({ json: claimGraphFixture() }));
  await page.goto("/report/loading-graph");
  await expect(page.getByRole("tab", { name: "Claim graph" })).toBeVisible();
  let release!: () => void;
  const ready = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/_next/static/chunks/*.js", async route => { await ready; await route.continue(); });
  try { await page.getByRole("tab", { name: "Claim graph" }).click(); await expect(page.getByRole("status", { name: "Loading claim graph" })).toBeVisible(); }
  finally { release(); }
  await expect(page.getByTestId("claim-graph-canvas")).toBeVisible();
});

for (const width of [1440, 390]) test(`peer review and claim graph share report navigation at ${width}px`, async ({ page }) => {
  const report = reviewFixture(), errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.setViewportSize({ width, height: 1000 });
  await page.route("**/jobs/both-tabs", route => route.fulfill({ json: report }));
  await page.goto("/report/both-tabs");
  await page.getByRole("tab", { name: "Peer review", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Area chair" })).toBeVisible();
  await page.getByRole("link", { name: report.review!.top_fixes![0], exact: true }).click();
  await expect(page.locator('[id="sentence-s1"]')).toBeFocused();
  await page.getByRole("tab", { name: "Claim graph", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Claim graph", exact: true })).toHaveCount(1);
  if (width < 640) await page.getByRole("list", { name: "Claim graph list" }).getByRole("button", { name: /Fixture trial 2/ }).click();
  else { await page.getByTestId("rf__edge-citation:claim-2:cite-2").focus(); await page.keyboard.press("Enter"); }
  await page.getByRole("dialog").getByRole("button", { name: "Open in evidence panel" }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Evidence receipt" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-citation-id="cite-2"]')).toBeInViewport();
  await expect(page.locator('[id="sentence-s1"]')).toHaveAttribute("data-highlighted", "false");
  await page.getByRole("tab", { name: "Peer review", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Area chair" })).toBeVisible();
  expect(errors).toEqual([]);
});
