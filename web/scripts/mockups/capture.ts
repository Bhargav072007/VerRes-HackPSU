import { chromium } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

async function main() {
const output = path.resolve("scripts/mockups/work/captures");
await mkdir(output, { recursive: true });
const reports = await Promise.all([2, 3].map(async n => JSON.parse(await readFile(`tests/fixtures/prod/paper${n}-job.json`, "utf8"))));
const browser = await chromium.launch({ channel: "chrome" });
const base = process.env.CAPTURE_URL || "http://127.0.0.1:3100";
const context = await browser.newContext({ deviceScaleFactor: 2, reducedMotion: "reduce" });
const page = await context.newPage();
for (const report of reports) await page.route(`**/jobs/${report.job_id}`, route => route.fulfill({ json: report }));
await page.route("**/jobs/*/events", route => route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" }));
const report = reports[1];
await page.setViewportSize({ width: 1512, height: 982 });
await page.goto(`${base}/report/${report.job_id}`);
await page.getByRole("heading", { name: report.paper.title }).waitFor();
await page.evaluate(() => document.fonts.ready);
await page.getByRole("article", { name: "Paper text" }).scrollIntoViewIfNeeded();
await page.screenshot({ path: `${output}/report-desktop.png` });
await page.setViewportSize({ width: 393, height: 852 });
await page.locator('[data-citation-id="c00003"]').scrollIntoViewIfNeeded();
await page.screenshot({ path: `${output}/report-mobile.png` });
await page.setViewportSize({ width: 1366, height: 1024 });
await page.getByRole("tab", { name: "Claim graph", exact: true }).click();
await page.locator(".react-flow__node").first().waitFor();
await page.getByRole("region", { name: "Claim graph", exact: true }).scrollIntoViewIfNeeded();
await page.screenshot({ path: `${output}/claim-graph.png` });
await page.setViewportSize({ width: 1512, height: 982 });
await page.getByRole("tab", { name: "Report", exact: true }).click();
if (process.env.CAPTURE_EVIDENCE === "1") {
  await page.locator('[data-citation-id="c00003"]').click();
  await page.getByRole("dialog").waitFor();
  await page.screenshot({ path: `${output}/evidence.png` });
  await page.keyboard.press("Escape");
}
await page.goto(`${base}/report/${reports[0].job_id}`);
await page.locator('[data-source-id="b0"]').waitFor();
await page.locator('[data-source-id="b0"]').screenshot({ path: `${output}/retraction.png` });
const events = (await readFile("../fixtures/demo/paper3.jsonl", "utf8")).trim().split("\n").map(line => JSON.parse(line));
const stop = events.findIndex(e => e.type === "support_result");
await page.route("**/jobs/d15-live", route => route.fulfill({ json: { events: events.slice(0, stop > 0 ? stop : Math.floor(events.length / 2)) } }));
await page.goto(`${base}/check/d15-live`);
await page.locator(".live-header").waitFor();
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: `${output}/live-check.png` });
await browser.close();
console.log(`Captured real fixture views in ${output}`);
}
void main();
