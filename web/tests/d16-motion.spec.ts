import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const heroAt = (page: Page, p: number) => page.evaluate(p => { const s = document.querySelector<HTMLElement>(".hero-scene")!; scrollTo({ top: s.offsetTop + p * (s.offsetHeight - innerHeight), behavior: "instant" }); }, p);
const transformOf = (page: Page, selector: string) => page.locator(selector).first().evaluate(n => getComputedStyle(n).transform);

test("D16 uses one motion engine and no smooth-scroll layer", () => {
  const pkg = JSON.parse(readFileSync("package.json", "utf8"));
  const deps = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
  expect(deps.filter(d => /gsap|lenis|locomotive|framer-motion/.test(d))).toEqual([]);
  const css = readFileSync("app/globals.css", "utf8");
  expect(css).not.toMatch(/view-timeline|animation-timeline|--beat/);
});

test("D16 desktop hero: one pinned scene at most 220vh, cards fly in and land as chips", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/");
  const sticky = await page.evaluate(() => [...document.querySelectorAll("main *")].filter(n => getComputedStyle(n).position === "sticky" && !n.closest(".stepper-rail")).map(n => n.className));
  expect(sticky).toEqual(["hero-stage"]);
  expect(await page.locator(".hero-scene").evaluate(n => (n as HTMLElement).offsetHeight / innerHeight)).toBeLessThanOrEqual(2.2);
  await expect(page.locator(".hero-card")).toHaveCount(8);
  await expect(page.locator(".hero-scroll-caption")).toHaveText("Scroll. Eight references, one reviewed page.");
  for (const node of await page.locator(".hero-stage :is(.hero-card p,.hero-card .finding-label,.paper-slot,.hero-tally li,.hero-scroll-caption)").all()) expect(parseFloat(await node.evaluate(n => getComputedStyle(n).fontSize))).toBeGreaterThanOrEqual(14);
  await heroAt(page, 0);
  await expect.poll(() => page.locator(".paper-slot-fill").first().evaluate(n => getComputedStyle(n).opacity)).toBe("0");
  await heroAt(page, .3);
  await expect.poll(() => transformOf(page, ".hero-card-flight")).not.toBe("none");
  await heroAt(page, 1);
  await expect.poll(() => page.locator(".paper-slot-fill").evaluateAll(ns => ns.every(n => getComputedStyle(n).opacity === "1"))).toBe(true);
  await expect.poll(() => page.locator(".hero-card-flight").evaluateAll(ns => ns.every(n => getComputedStyle(n).opacity === "0"))).toBe(true);
  await expect(page.locator(".hero-paper")).toHaveCSS("transform", /^(none|matrix\(([\d.]+), 0, 0, \2, 0, 0\))$/);
});

test("D16 mobile hero does not pin; chips pop once in view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto("/");
  await expect(page.locator(".hero-stage")).not.toHaveCSS("position", "sticky");
  await expect(page.locator(".hero-card")).toHaveCount(0);
  await page.locator(".paper-references").scrollIntoViewIfNeeded();
  await expect.poll(() => page.locator(".paper-slot-fill").evaluateAll(ns => ns.every(n => getComputedStyle(n).opacity === "1"))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const how of ["os", "reader"] as const) test(`D16 reduced motion (${how}) shows final states with identical layout`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/"); const layout = await page.locator(".hero-scene").evaluate(n => (n as HTMLElement).offsetHeight);
  if (how === "os") await page.emulateMedia({ reducedMotion: "reduce" }); else await page.evaluate(() => { document.documentElement.dataset.a11yMotion = "reduce"; });
  expect(await page.locator(".hero-scene").evaluate(n => (n as HTMLElement).offsetHeight)).toBe(layout);
  await heroAt(page, 0);
  await expect(page.locator(".hero-paper")).toHaveCSS("transform", /^(none|matrix\(([\d.]+), 0, 0, \2, 0, 0\))$/);
  await expect.poll(() => page.locator(".paper-slot-fill").evaluateAll(ns => ns.every(n => getComputedStyle(n).opacity === "1"))).toBe(true);
  await expect.poll(() => page.locator(".hero-card-flight").evaluateAll(ns => ns.every(n => getComputedStyle(n).opacity === "0"))).toBe(true);
  await page.locator("[data-stage-card='5']").scrollIntoViewIfNeeded();
  await expect(page.locator("[data-stage-card='5'] .hero-chip")).toHaveCSS("opacity", "1");
  await expect(page.locator(".blur-reveal")).toHaveCSS("filter", "none");
  await expect(page.locator(".phone-focus")).toHaveCSS("filter", "none");
});

test("D16 sticky nav, stepper rail, blur, cl-flash and dot matrix", async ({ page }) => {
  const errors: string[] = []; page.on("pageerror", e => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/");
  const bar = page.locator(".sticky-nav");
  await expect(bar).toHaveAttribute("data-shown", "false");
  await page.locator("[data-stage-card='3']").evaluate(n => n.scrollIntoView({ block: "center", behavior: "instant" }));
  await expect(bar).toHaveAttribute("data-shown", "true");
  await expect(bar.locator(".sticky-nav-label")).toHaveText("02 · How it works");
  await expect(bar.getByRole("link", { name: "Method" })).toHaveAttribute("aria-current", "location");
  expect(await bar.locator(".sticky-nav-progress").evaluate(n => new DOMMatrixReadOnly(getComputedStyle(n).transform).a)).toBeGreaterThan(0);
  await expect(page.locator(".stepper-rail [aria-current=step]")).toContainText("Retraction");
  await expect(page.locator(".stepper-rail [data-complete=true]")).toHaveCount(2);
  await expect(page.locator(".rail-progress")).toHaveText("Stage 3 of 6");
  await expect(page.locator("[data-stage-card='3'] .demo-stamp")).toHaveText("Retracted 2010");
  const heading = page.locator(".blur-reveal");
  expect(await heading.evaluate(n => getComputedStyle(n).filter)).toBe("blur(8px)");
  await heading.evaluate(n => n.scrollIntoView({ block: "center", behavior: "instant" }));
  await expect.poll(() => heading.evaluate(n => getComputedStyle(n).filter)).toBe("blur(0px)");
  await expect(bar.locator(".sticky-nav-label")).toHaveText("05 · Limitations");
  const row = page.locator(".excerpt-row").nth(1); await row.scrollIntoViewIfNeeded();
  await row.locator(".margin-note").click();
  await expect.poll(() => row.locator(".excerpt-text .note-tint").last().evaluate(n => +getComputedStyle(n).opacity)).toBeGreaterThan(0);
  const canvas = page.locator(".dot-matrix canvas"); await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!; await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 4 });
  await expect(page.locator(".dot-matrix figcaption")).toHaveText("Move through it.");
  expect(errors).toEqual([]);
});
