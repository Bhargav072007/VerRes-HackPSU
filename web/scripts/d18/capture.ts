/** CAPTURE_URL=http://127.0.0.1:3106 npx tsx scripts/d18/capture.ts — D18 screenshots into docs/d18 (review room fed recorded paper 3 events). */
import { chromium, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import sharp from "sharp";
const base = process.env.CAPTURE_URL || "http://127.0.0.1:3106", out = "docs/d18";
const events = readFileSync("../fixtures/demo/paper3.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line));
const save = async (page: Page, name: string) => sharp(await page.screenshot()).webp({ quality: 86 }).toFile(`${out}/${name}.webp`);
async function main() {
  const browser = await chromium.launch({ channel: "chrome" });
  for (const theme of ["light", "dark"] as const) for (const [width, height, suffix] of [[1440, 900, "1440"], [390, 844, "390"]] as const) {
    if (width === 390 && theme === "dark") continue;
    const page = await browser.newPage({ viewport: { width, height } });
    await page.addInitScript(t => { try { localStorage.setItem("verres-theme", t); } catch { /* optional */ } }, theme);
    await page.route("**/status", r => r.fulfill({ json: {} }));
    for (const [id, count] of [["room-mid", 40], ["room-done", events.length]] as const) {
      await page.route(`**/jobs/${id}`, r => r.fulfill({ json: { events: events.slice(0, count) } }));
      await page.route(`**/jobs/${id}/events`, r => r.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
    }
    await page.goto(base); await page.evaluate(() => document.fonts.ready);
    if (width === 1440) { await page.evaluate(() => { const s = document.querySelector<HTMLElement>(".hero-scene")!; scrollTo({ top: s.offsetTop + s.offsetHeight - innerHeight, behavior: "instant" }); }); await page.waitForTimeout(900); }
    else { await page.locator(".hero-tally").evaluate(n => n.scrollIntoView({ block: "end", behavior: "instant" })); await page.waitForTimeout(1800); }
    await save(page, `hero-p1-${theme}-${suffix}`);
    await page.goto(`${base}/check/room-mid`); await page.locator(".agent-card").first().waitFor(); await page.waitForTimeout(600);
    await page.locator(".room-top").evaluate(n => n.scrollIntoView({ block: "start", behavior: "instant" }));
    await save(page, `room-mid-${theme}-${suffix}`);
    if (width === 1440) {
      await page.goto(`${base}/check/room-done`); await page.locator(".room-done").waitFor(); await page.mouse.move(8, 8); await page.waitForTimeout(800);
      await page.locator(".room-top").evaluate(n => n.scrollIntoView({ block: "start", behavior: "instant" }));
      await save(page, `room-done-${theme}-${suffix}`);
      if (theme === "dark") { await page.goto(`${base}/report/sample-paper3`); await page.getByRole("article", { name: "Paper text" }).waitFor(); await page.waitForTimeout(500); await save(page, `report-dark-${suffix}`); }
    }
    await page.close();
  }
  await browser.close(); console.log(`Saved screenshots to ${out}.`);
}
void main();
