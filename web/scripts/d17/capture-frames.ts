/** CAPTURE_URL=http://127.0.0.1:3105 CAPTURE_OUT=docs/d17 npx tsx scripts/d17/capture-frames.ts [hero] [phone] [logo] */
import { chromium, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import sharp from "sharp";
const base = process.env.CAPTURE_URL || "http://127.0.0.1:3105", out = process.env.CAPTURE_OUT || "docs/d17";
const only = process.argv.slice(2), want = (name: string) => !only.length || only.includes(name);
const save = async (page: Page, name: string) => sharp(await page.screenshot()).webp({ quality: 88 }).toFile(`${out}/${name}.webp`);
// Pinned hero: progress p across the scene's scroll length.
const heroAt = (page: Page, p: number) => page.evaluate(p => { const s = document.querySelector<HTMLElement>(".hero-scene")!; scrollTo({ top: s.offsetTop + p * (s.offsetHeight - innerHeight), behavior: "instant" }); }, p);
// Phone section: progress with offset ["start end", "end start"].
const phoneAt = (page: Page, p: number) => page.evaluate(p => { const s = document.getElementById("anywhere")!; scrollTo({ top: s.offsetTop - innerHeight + p * (innerHeight + s.offsetHeight), behavior: "instant" }); }, p);
async function main() {
  await mkdir(out, { recursive: true });
  const browser = await chromium.launch({ channel: "chrome" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await page.goto(base); await page.evaluate(() => document.fonts.ready);
  await page.evaluate(async () => { for (const image of Array.from(document.images)) { image.loading = "eager"; await image.decode().catch(() => {}); } });
  if (want("hero")) for (const p of [0, .3, .6, 1]) { await heroAt(page, p); await page.waitForTimeout(700); await save(page, `hero-p${String(p).replace(".", "")}-1440`); }
  if (want("phone")) for (const [p, name] of [[.18, "entering"], [.5, "centred"], [.84, "leaving"]] as const) { await phoneAt(page, p); await page.waitForTimeout(400); await save(page, `phone-${name}-1440`); }
  if (want("logo")) {
    const canvas = page.locator(".dot-logo canvas");
    await canvas.evaluate(n => n.scrollIntoView({ block: "center", behavior: "instant" }));
    await page.waitForTimeout(120); await save(page, "logo-scattered-1440");
    await page.waitForTimeout(1800); await save(page, "logo-assembled-1440");
    const box = (await canvas.boundingBox())!;
    await page.mouse.move(box.x + box.width * .3, box.y + box.height * .5);
    await page.mouse.move(box.x + box.width * .48, box.y + box.height * .46, { steps: 10 });
    await page.waitForTimeout(250); await save(page, "logo-pointer-1440");
  }
  await browser.close(); console.log(`Saved frames to ${out}.`);
}
void main();
