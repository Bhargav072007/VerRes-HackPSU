/** CAPTURE_URL=http://127.0.0.1:3105 npx tsx scripts/mockups/capture.ts
 * Reuses selected scenes; captures real fixtures at deviceScaleFactor 2.
 */
import { chromium } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
async function main() {
 const output=path.resolve("scripts/mockups/work/captures"); await mkdir(output,{recursive:true});
 const reports=await Promise.all([2,3].map(async n=>JSON.parse(await readFile(`tests/fixtures/prod/paper${n}-job.json`,"utf8"))));
 const browser=await chromium.launch({channel:"chrome"});
 const context=await browser.newContext({deviceScaleFactor:2,reducedMotion:"reduce"});
 const page=await context.newPage(); const base=process.env.CAPTURE_URL||"http://127.0.0.1:3105";
 for(const report of reports)await page.route(`**/jobs/${report.job_id}`,route=>route.fulfill({json:report}));
 await page.route("**/jobs/*/events",route=>route.fulfill({contentType:"text/event-stream",body:"retry: 60000\n\n"}));
 const ready=async()=>{await page.evaluate(()=>document.fonts.ready);};
 const position=async(selector:string,top=180)=>{await page.locator(selector).evaluate((n,t)=>window.scrollTo({top:scrollY+n.getBoundingClientRect().top-t,behavior:"instant"}),top);await page.waitForTimeout(180);};
 await page.setViewportSize({width:1280,height:800});
 await page.goto(`${base}/report/${reports[1].job_id}`);await page.getByRole("heading",{name:reports[1].paper.title}).waitFor();await ready();
 await position('[data-sentence-id="s00005"]',210);await page.screenshot({path:`${output}/report-desktop.png`});
 await page.setViewportSize({width:393,height:852});await position('[data-sentence-id="s00005"]',185);await page.screenshot({path:`${output}/report-mobile.png`});
 await page.setViewportSize({width:1024,height:768});await page.locator('[data-citation-id="c00003"]').click();await page.getByRole("dialog").waitFor();await ready();await page.screenshot({path:`${output}/evidence.png`});
 await page.getByRole("dialog").screenshot({path:`${output}/method-evidence.png`});await page.keyboard.press("Escape");
 await page.setViewportSize({width:1280,height:800});
 for(const [name,id]of [["exists","b3"],["doi","b4"]]){const source=page.locator(`[data-source-id="${id}"]`);await source.locator("summary").click();await source.screenshot({path:`${output}/method-${name}.png`});}
 await page.getByRole("region",{name:"Hidden text findings"}).screenshot({path:`${output}/method-hidden.png`});
 await page.getByRole("tab",{name:"Peer review",exact:true}).click();await page.getByRole("heading",{name:"Area chair",exact:true}).waitFor();await position('[role="tabpanel"]',80);await page.screenshot({path:`${output}/method-review.png`});
 await page.goto(`${base}/report/${reports[0].job_id}`);const retraction=page.locator('[data-source-id="b0"]');await retraction.waitFor();await retraction.locator("summary").click();await retraction.screenshot({path:`${output}/method-retraction.png`});
 const events=(await readFile("../fixtures/demo/paper3.jsonl","utf8")).trim().split("\n").map(line=>JSON.parse(line));const stop=events.findIndex(e=>e.type==="support_result");
 await page.route("**/jobs/d15-live",route=>route.fulfill({json:{events:events.slice(0,stop>0?stop:Math.floor(events.length/2))}}));
 await page.goto(`${base}/check/d15-live`);await page.locator(".live-header").waitFor();await ready();await page.screenshot({path:`${output}/live-check.png`});
 await browser.close();console.log(`Captured final fixture views in ${output}`);
}
void main();
