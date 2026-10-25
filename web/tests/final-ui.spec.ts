import { test, expect } from "@playwright/test";
import { reviewFixture } from "./fixtures/review";

for (const width of [1440, 390]) test(`D15 landing, facts, method and sample at ${width}px`, async ({page}) => {
 await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:"reduce"});await page.goto("/");await page.evaluate(()=>document.fonts.ready);
 await expect(page.getByRole("heading",{name:"Read your paper like Reviewer 2 would."})).toBeVisible();
 await expect(page.locator('.trust-columns>div')).toHaveCount(3);
 await expect(page.locator('.trust-columns')).toContainText('checks per citation');
 await expect(page.locator('.trust-columns')).toContainText('scholarly sources');
 await expect(page.locator('.trust-columns')).toContainText('median review time, recorded runs');
 await expect(page.getByText('Every finding links to its evidence.',{exact:true})).toHaveCount(1);
 await expect(page.locator('.paper-references')).toContainText('Partially supported');
 await expect(page.locator('.paper-slot')).toHaveCount(8);
 const runtime=page.locator('.trust-columns .large-numeral').last();
 await expect(runtime).toHaveCSS('white-space','nowrap');
 await expect(runtime.locator('small')).toHaveCSS('vertical-align','baseline');
 expect(await runtime.evaluate(node=>node.getBoundingClientRect().right<=node.parentElement!.getBoundingClientRect().right)).toBe(true);
 await expect(page.locator('.trust-band')).toHaveScreenshot(`trust-${width}.png`,{animations:'disabled'});
 for(const number of await page.locator('.paper-excerpt .line-number').all()){
  await expect(number).toHaveCSS('white-space','nowrap');
  await expect(number).toHaveCSS('font-variant-numeric','tabular-nums');
  expect(await number.evaluate(node=>node.scrollWidth<=node.clientWidth)).toBe(true);
 }
 await expect(page.locator('.paper-excerpt')).toHaveScreenshot(`excerpt-${width}.png`,{animations:'disabled'});
 await expect(page.locator('.sample-heading')).toHaveCSS('color','rgb(255, 255, 255)');
 await expect(page.locator('.sample-papers')).toHaveScreenshot(`sample-cta-${width}.png`,{animations:'disabled'});
 await expect(page.locator('[data-stage-card]')).toHaveCount(6);
 await expect(page.locator('[data-stage-card="3"]')).toContainText('Retracted 2010');
 await expect(page.locator('[data-stage-card="3"] a',{hasText:'Retraction notice'})).toHaveAttribute('href','https://doi.org/10.1016/s0140-6736%2810%2960175-4');
 await expect(page.locator('.paper-excerpt .margin-note')).toHaveCount(3);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('link',{name:'See a sample report'}).click();await expect(page.getByRole('article',{name:'Paper text'})).toBeVisible();
 await expect(page.locator('[data-citation-id="c00003"]')).toHaveAttribute('aria-label',/Partially supported/);
 for(const row of await page.locator('.summary-table tbody tr').all()){
  const count=await row.locator('td').last().textContent();
  if(count==='0'){
   await expect(row.locator('td').first()).toHaveText('None found');
   await expect(row.locator('td').first()).toHaveClass('text-muted-foreground');
  }
 }
 await expect(page.locator('.summary-table')).toHaveScreenshot(`summary-${width}.png`,{animations:'disabled'});
 for(const number of await page.locator('.paragraph-number').all()){
  await expect(number).toHaveCSS('white-space','nowrap');
  await expect(number).toHaveCSS('font-variant-numeric','tabular-nums');
  expect(await number.evaluate(node=>node.scrollWidth<=node.clientWidth)).toBe(true);
 }
});

for (const width of [1440, 390]) test(`D14 reader preferences persist, themes cover overlays, and hover-to-cite at ${width}px`, async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.setViewportSize({ width, height: 900 });
  await page.route("**/jobs/reader", route => route.fulfill({ json: reviewFixture() }));
  await page.route("http://localhost:8000/shares/reader", route => route.fulfill({ json: { ...reviewFixture(), shared: true } }));
  for (const route of ["/report/reader", "/shares/reader"]) {
    await page.goto(route);
    for (const theme of ["light", "sepia", "dark"]) {
      await page.getByRole("button", { name: "Reader settings", exact: true }).click();
      const settings = page.getByRole("dialog", { name: "Reader settings", exact: true });
      await settings.getByRole("button", { name: theme, exact: true }).click();
      await expect(page.locator("html")).toHaveAttribute("data-reader-theme", theme);
      await settings.getByLabel("Text size", { exact: true }).fill("20");
      await settings.getByRole("button", { name: "open", exact: true }).click();
      await settings.getByRole("button", { name: "narrow", exact: true }).click();
      await settings.getByRole("button", { name: "sans", exact: true }).click();
      await settings.getByLabel("Reduce motion", { exact: true }).check();
      await page.screenshot({ animations: "disabled", path: info.outputPath(`settings-${route.startsWith('/shares') ? 'shared' : 'report'}-${theme}-${width}.png`) });
      await page.keyboard.press("Escape");
      await expect(page.getByRole("button", { name: "Reader settings", exact: true })).toBeFocused();
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-reader-theme", theme);
      await expect(page.locator("html")).toHaveAttribute("data-a11y-motion", "reduce");
      await expect(page.locator(".reader-paragraph").first()).toHaveCSS("font-size", "20px");
      await expect(page.locator(".reader-paragraph").first()).toHaveCSS("line-height", "40px");
      await page.screenshot({ animations: "disabled", path: info.outputPath(`report-${route.startsWith('/shares') ? 'shared' : 'private'}-${theme}-${width}.png`) });
    }
    const marker = page.locator('[data-citation-id="cite-2"]');
    await marker.scrollIntoViewIfNeeded();
    await marker.hover();
    await expect(marker.getByRole("tooltip")).toBeVisible();
    await expect(marker.getByRole("tooltip")).toContainText("Fixture trial 2");
    await expect(marker.getByRole("tooltip")).toContainText("children were not enrolled.");
    await marker.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark"); // One theme for the site: the report's choice carries over.
  await expect(page.locator(".hero-paper")).toHaveCSS("transform", /^(none|matrix\(([\d.]+), 0, 0, \2, 0, 0\))$/);
  await expect(page.locator("html")).not.toHaveAttribute("data-landing-scroll");
  expect(errors).toEqual([]);
});

test("D14 reader remains usable when localStorage is blocked", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.addInitScript(() => Object.defineProperty(window, "localStorage", { get() { throw new DOMException("Storage blocked", "SecurityError"); } }));
  await page.route("**/jobs/blocked", route => route.fulfill({ json: reviewFixture() }));
  await page.goto("/report/blocked");
  await page.getByRole("button", { name: "Reader settings", exact: true }).click();
  await page.getByRole("dialog", { name: "Reader settings" }).getByRole("button", { name: "sepia", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-reader-theme", "sepia");
  await page.keyboard.press("Escape");
  await expect(page.locator(".reader-paragraph").first()).toHaveCSS("font-size", "18px");
  expect(errors).toEqual([]);
});
