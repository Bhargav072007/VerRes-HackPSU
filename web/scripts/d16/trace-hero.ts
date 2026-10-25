/** CAPTURE_URL=http://127.0.0.1:3105 npx tsx scripts/d16/trace-hero.ts — Chrome trace of a wheel scroll through the hero scene. */
import { chromium } from "@playwright/test";
import { writeFile } from "node:fs/promises";
type Event = { name: string; ph: string; ts: number; dur?: number; pid: number; tid: number; args?: { data?: { frame?: string } } };
const base = process.env.CAPTURE_URL || "http://127.0.0.1:3105";
async function main() {
  const browser = await chromium.launch({ channel: "chrome" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(base); await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(1000);
  const distance = await page.locator(".hero-scene").evaluate(n => (n as HTMLElement).offsetTop + (n as HTMLElement).offsetHeight);
  await browser.startTracing(page, { categories: ["devtools.timeline", "disabled-by-default-devtools.timeline", "toplevel"] });
  for (let y = 0; y < distance; y += 60) { await page.mouse.wheel(0, 60); await page.waitForTimeout(16); }
  await page.waitForTimeout(500);
  const { traceEvents } = JSON.parse((await browser.stopTracing()).toString()) as { traceEvents: Event[] };
  await browser.close();
  // The renderer main thread is the one running the page's script.
  const main = traceEvents.find(e => e.name === "FunctionCall" || e.name === "EvaluateScript")!;
  const thread = traceEvents.filter(e => e.pid === main.pid && e.tid === main.tid && e.ph === "X");
  const tasks = thread.filter(e => e.name === "RunTask" || e.name === "ThreadControllerImpl::RunTask");
  const scripts = thread.filter(e => ["FunctionCall", "EvaluateScript", "TimerFire", "FireAnimationFrame", "EventDispatch"].includes(e.name));
  const layouts = thread.filter(e => e.name === "Layout");
  // A layout that runs inside a script call was forced synchronously (read-after-write): that is layout thrash.
  const forced = layouts.filter(l => scripts.some(s => l.ts >= s.ts && l.ts + (l.dur ?? 0) <= s.ts + (s.dur ?? 0)));
  const longest = Math.max(0, ...tasks.map(t => (t.dur ?? 0) / 1000));
  const summary = { url: base, viewport: "1440x900", scrolledPx: distance, tasks: tasks.length, longTasksOver50ms: tasks.filter(t => (t.dur ?? 0) > 50_000).length, longestTaskMs: +longest.toFixed(1), layouts: layouts.length, forcedLayoutsInScript: forced.length, totalLayoutMs: +(layouts.reduce((n, l) => n + (l.dur ?? 0), 0) / 1000).toFixed(1) };
  await writeFile("docs/d16/hero-scroll-trace.json", JSON.stringify(summary, null, 2) + "\n");
  console.log(summary);
}
void main();
