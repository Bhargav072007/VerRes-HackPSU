import { test, expect } from "@playwright/test";
import { reviewFixture } from "./fixtures/review";

for (const width of [1440, 390]) test(`D14 manuscript, assets and section figures at ${width}px`, async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveTitle("VerRes — read your paper like Reviewer 2 would");
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute("content", /\/brand\/og-image.png$/);
  await expect(page.locator('link[rel="icon"][href="/favicon.ico"]')).toHaveCount(1);
  for (const asset of ["verres-lockup.png", "verres-mark.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "og-image.png"]) expect((await page.request.get(`/brand/${asset}`)).ok()).toBe(true);
  await expect(page.getByText("Illustrative composite.", { exact: true })).toBeVisible();
  await page.screenshot({ animations: "disabled", path: info.outputPath(`landing-top-${width}.png`) });
  const scene = page.locator(".manuscript-sequence");
  if (width === 1440) {
    await expect(scene).not.toHaveAttribute("data-static");
    expect(await scene.evaluate(n => n.getBoundingClientRect().height - innerHeight)).toBe(2700);
    for (const beat of [1, 2, 3, 4, 5, 4, 3, 2, 1]) {
      await scene.evaluate((n, b) => window.scrollTo({ top: window.scrollY + n.getBoundingClientRect().top + ((b - 1 + .85) / 5) * innerHeight * 3, behavior: "instant" }), beat);
      await expect.poll(() => scene.evaluate((n, b) => Number(getComputedStyle(n).getPropertyValue(`--beat-${b}`)), beat)).toBe(1);
      if (beat < 5) await expect.poll(() => scene.evaluate((n, b) => Number(getComputedStyle(n).getPropertyValue(`--beat-${b + 1}`)), beat)).toBe(0);
      if (beat === 3) await page.screenshot({ animations: "disabled", path: info.outputPath(`landing-sequence-${width}.png`) });
    }
  } else {
    await expect(scene).toHaveAttribute("data-static");
    await expect(page.locator(".static-beat-captions li")).toHaveCount(5);
    await page.locator(".manuscript-page").scrollIntoViewIfNeeded();
    await page.screenshot({ animations: "disabled", path: info.outputPath(`landing-sequence-${width}.png`) });
  }
  for (const section of ["abstract", "how-it-works", "results", "honesty", "submit"]) {
    await page.locator(`#${section}`).evaluate(node => node.scrollIntoView({ block: "start", behavior: "instant" }));
    await expect(page.locator(`#${section} h2`).first()).toBeInViewport();
    await expect(page.locator(`#${section} [data-enter]`).first()).toHaveCSS("opacity", "1");
    if (section === "results" || section === "how-it-works") await expect(page.locator(`#${section} article`).first()).toHaveCSS("opacity", "1");
    await page.screenshot({ animations: "disabled", path: info.outputPath(`landing-${section}-${width}.png`) });
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("D14 reduced motion is static and Lenis stays off report and check routes", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.locator(".manuscript-sequence")).toHaveAttribute("data-static");
  for (let beat = 1; beat <= 5; beat++) await expect.poll(() => page.locator(".manuscript-sequence").evaluate((n, b) => Number(getComputedStyle(n).getPropertyValue(`--beat-${b}`)), beat)).toBe(1);
  await expect(page.locator("html")).not.toHaveAttribute("data-landing-scroll");
  await page.route("**/jobs/reader", route => route.fulfill({ json: reviewFixture() }));
  await page.goto("/report/reader");
  await expect(page.getByRole("button", { name: "Reader settings", exact: true })).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-landing-scroll");
  await page.route("**/jobs/live", route => route.fulfill({ json: { events: [] } }));
  await page.route("**/jobs/live/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
  await page.goto("/check/live");
  await expect(page.locator(".live-header")).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-landing-scroll");
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
  await expect(page.locator("html")).toHaveAttribute("data-reader-theme", "light");
  await expect(page.locator(".manuscript-sequence")).toHaveAttribute("data-static");
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
