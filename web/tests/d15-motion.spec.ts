import { test, expect } from "@playwright/test";
import paper from "./fixtures/prod/paper3-job.json";
test("D15 first-view counts reserve space; hero parallax is bounded and reduced motion stops it",async({page})=>{
 await page.setViewportSize({width:1440,height:900});await page.goto("/");
 const count=page.locator('.count-once').first();await count.scrollIntoViewIfNeeded();const before=await count.boundingBox();await expect(count).toHaveText('6');expect((await count.boundingBox())!.width).toBeCloseTo(before!.width,1);
 await page.locator('h1').scrollIntoViewIfNeeded();await count.scrollIntoViewIfNeeded();await expect(count).toHaveText('6');
 const crops=page.locator('.hero-details');await crops.scrollIntoViewIfNeeded();const box=(await crops.boundingBox())!;await page.mouse.move(box.x+box.width-10,box.y+box.height-10);
 await expect.poll(()=>crops.evaluate(n=>Math.abs(new DOMMatrixReadOnly(getComputedStyle(n).transform).m41))).toBeGreaterThan(0);
 const matrix=await crops.evaluate(n=>{const m=new DOMMatrixReadOnly(getComputedStyle(n).transform);return [m.m41,m.m42];});expect(matrix.every(n=>Math.abs(n)<=6)).toBe(true);
 await page.emulateMedia({reducedMotion:'reduce'});await expect(crops).toHaveCSS('transform','none');await expect(count).toHaveText('6');
});
test("D15 evidence links tint the paired line and note on landing and report",async({page})=>{
 await page.setViewportSize({width:1440,height:900});await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');
 const row=page.locator('.excerpt-row').nth(1);await row.locator('.margin-note').hover();await expect(row.locator('.excerpt-text .note-tint')).toHaveCSS('opacity','0.09');
 await row.locator('.excerpt-text').hover();await expect(row.locator('.margin-note .note-tint')).toHaveCSS('opacity','0.09');
 await page.route(`**/jobs/${paper.job_id}`,r=>r.fulfill({json:paper}));await page.goto(`/report/${paper.job_id}`);
 const reportRow=page.locator('.reader-row').filter({has:page.locator('[data-sentence-id="s00005"]')});await reportRow.locator('.margin-note').hover();await expect(reportRow.locator('.reader-paragraph .note-tint')).toHaveCSS('opacity','0.09');
 await reportRow.locator('.reader-paragraph').hover();await expect(reportRow.locator('.margin-note .note-tint')).toHaveCSS('opacity','0.09');
});
