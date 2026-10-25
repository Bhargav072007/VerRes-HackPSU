import { test, expect, type Page } from "@playwright/test";
import { findingStyles, type HeroChip } from "../lib/landing-data";

const rgb = (hex: string) => `rgb(${[1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)).join(", ")})`;
const heroAt = (page: Page, p: number) => page.evaluate(p => { const s = document.querySelector<HTMLElement>(".hero-scene")!; scrollTo({ top: s.offsetTop + p * (s.offsetHeight - innerHeight), behavior: "instant" }); }, p);

test("D17 hero slots fill with their fixture verdicts in the right colours", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/");
  await expect(page.locator(".paper-slot[data-filled=true]")).toHaveCount(0);
  await heroAt(page, 1);
  await expect(page.locator(".paper-slot[data-filled=true]")).toHaveCount(8);
  for (const slot of await page.locator(".paper-slot").all()) {
    const chip = (await slot.getAttribute("data-chip")) as HeroChip, style = findingStyles[chip];
    await expect(slot.locator(".paper-slot-bar")).toHaveCSS("background-color", rgb(style.color));
    await expect(slot.locator(".finding-label")).toHaveCSS("color", rgb(style.text));
    await expect(slot.locator(".finding-label")).toHaveText(style.label);
    await expect(slot.locator(".paper-slot-verdict")).toHaveCSS("opacity", "1");
  }
  await expect(page.locator('.paper-slot[data-slot="1"]')).toHaveAttribute("data-chip", "RETRACTED");
  await expect(page.locator(".hero-tally")).toHaveText(/2 supported.*1 partial.*1 not found.*1 DOI mismatch.*1 retracted.*2 needs review/);
  await expect(page.locator("img[src*='s1@'], img[src*='/s1.']")).toHaveCount(0);
});

test("D17 phone photo is sharp at the section centre and blurred while entering", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/");
  const at = (p: number) => page.evaluate(p => { const s = document.getElementById("anywhere")!; scrollTo({ top: s.offsetTop - innerHeight + p * (innerHeight + s.offsetHeight), behavior: "instant" }); }, p);
  const blur = () => page.locator(".phone-focus").evaluate(n => parseFloat(getComputedStyle(n).filter.replace(/[^\d.]/g, "")) || 0);
  await at(.1); await expect.poll(blur).toBeGreaterThan(4);
  await at(.5); await expect.poll(blur).toBe(0);
  await expect(page.locator(".phone-focus img")).toHaveAttribute("src", /iphone-report/);
});

test("D17 dot logo assembles in the logo's colours and bursts on click", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/");
  const canvas = page.locator(".dot-logo canvas");
  await canvas.evaluate(n => n.scrollIntoView({ block: "center", behavior: "instant" }));
  await expect(canvas).toHaveAttribute("data-state", "assembled", { timeout: 4000 });
  const [painted, warm] = await canvas.evaluate((c: HTMLCanvasElement) => { const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data; let n = 0, w = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) { n++; if (d[i] > 120 && d[i] >= d[i + 1] && d[i + 1] >= d[i + 2]) w++; } return [n, w]; });
  expect(painted).toBeGreaterThan(500);
  expect(warm / painted).toBeGreaterThan(.7);
  await canvas.click(); await expect(canvas).toHaveAttribute("data-state", "burst");
  await expect(canvas).toHaveAttribute("data-state", "assembled", { timeout: 3000 });
  await page.emulateMedia({ reducedMotion: "reduce" }); await page.reload();
  await expect(page.locator(".dot-logo canvas")).toHaveAttribute("data-state", "assembled");
});

test("D17 footer mark is a keyboard-focusable back-to-top control", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/");
  const mark = page.getByRole("button", { name: "Back to top" });
  await mark.scrollIntoViewIfNeeded();
  await page.getByRole("link", { name: "GitHub" }).focus(); await page.keyboard.press("Shift+Tab");
  await expect(mark).toBeFocused();
  await expect(mark.locator(".footer-mark-sheen")).toHaveCount(1);
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
});
