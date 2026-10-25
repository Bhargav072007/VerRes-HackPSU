/** CAPTURE_URL=http://127.0.0.1:3105 npx tsx scripts/mockups/capture-pages.ts */
import { chromium } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import sharp from "sharp";
async function main(){
 const browser=await chromium.launch({channel:"chrome"});
 const context=await browser.newContext({reducedMotion:"reduce",deviceScaleFactor:1});const page=await context.newPage();
 const base=process.env.CAPTURE_URL||"http://127.0.0.1:3105";await mkdir("docs/d15",{recursive:true});
 const paper=JSON.parse(await readFile("tests/fixtures/prod/paper3-job.json","utf8"));await page.route(`**/jobs/${paper.job_id}`,route=>route.fulfill({json:paper}));
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:900});await page.goto(base);await page.evaluate(()=>document.fonts.ready);
  await page.evaluate(async()=>{for(const image of Array.from(document.images)){image.loading="eager";await image.decode().catch(()=>{});}});
  await sharp(await page.screenshot({fullPage:true,animations:"disabled"})).webp({quality:90}).toFile(`docs/d15/landing-${width}.webp`);
  await page.goto(`${base}/report/${paper.job_id}`);await page.getByRole("heading",{name:paper.paper.title}).waitFor();await page.evaluate(()=>document.fonts.ready);
  for(const theme of ["light","dark"]){await page.getByRole("button",{name:"Reader settings",exact:true}).click();await page.getByRole("dialog",{name:"Reader settings",exact:true}).getByRole("button",{name:theme,exact:true}).click();await page.keyboard.press("Escape");await page.evaluate(()=>scrollTo({top:0,behavior:"instant"}));await sharp(await page.screenshot({fullPage:true,animations:"disabled"})).webp({quality:90}).toFile(`docs/d15/report-${theme}-${width}.webp`);}
 }
 await browser.close();console.log("Saved full-page landing and light/dark report captures at 1440 and 390.");
}
void main();
