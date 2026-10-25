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
