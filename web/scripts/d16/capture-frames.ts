/** CAPTURE_URL=http://127.0.0.1:3105 CAPTURE_OUT=docs/d16 npx tsx scripts/d16/capture-frames.ts [hero] [stepper] */
import { chromium, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import sharp from "sharp";
const base = process.env.CAPTURE_URL || "http://127.0.0.1:3105", out = process.env.CAPTURE_OUT || "docs/d16";
const only = process.argv.slice(2);
const save = async (page: Page, name: string) => sharp(await page.screenshot()).webp({ quality: 88 }).toFile(`${out}/${name}.webp`);
// Scroll so the pinned hero scene sits at progress p, then let motion settle the frame.
async function heroAt(page: Page, p: number) {
  await page.evaluate(p => { const s = document.querySelector<HTMLElement>(".hero-scene")!; scrollTo({ top: s.offsetTop + p * (s.offsetHeight - innerHeight), behavior: "instant" }); }, p);
  await page.waitForTimeout(450);
}
async function main() {
  await mkdir(out, { recursive: true });
  const browser = await chromium.launch({ channel: "chrome" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await page.goto(base); await page.evaluate(() => document.fonts.ready);
  await page.evaluate(async () => { for (const image of Array.from(document.images)) { image.loading = "eager"; await image.decode().catch(() => {}); } });
  if (!only.length || only.includes("hero")) for (const p of [0, .3, .6, .9]) { await heroAt(page, p); await save(page, `hero-p${String(p).replace(".", "")}-1440`); }
  if (!only.length || only.includes("stepper")) for (const stage of [1, 3, 5]) {
    await page.locator(`[data-stage-card="${stage}"]`).evaluate(node => node.scrollIntoView({ block: "center", behavior: "instant" }));
    await page.waitForTimeout(1600);
    await save(page, `stepper-stage${stage}-1440`);
  }
  await browser.close(); console.log(`Saved frames to ${out}.`);
}
void main();
