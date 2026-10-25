/** CAPTURE_URL=http://127.0.0.1:3105 npx tsx scripts/d17/og-image.ts — OG card from the hero H1 and the reviewed paper page (no photos). */
import { chromium } from "@playwright/test";
const base = process.env.CAPTURE_URL || "http://127.0.0.1:3105";
async function main() {
  const browser = await chromium.launch({ channel: "chrome" });
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, reducedMotion: "reduce" });
  await page.goto(base); await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => {
    const card = document.createElement("div"), h1 = document.querySelector("h1")!.cloneNode(true) as HTMLElement, paper = document.querySelector(".hero-paper")!.cloneNode(true) as HTMLElement;
    card.style.cssText = "position:fixed;inset:0;z-index:9999;display:grid;grid-template-columns:1fr 1.15fr;align-items:center;gap:40px;padding:0 56px;background:var(--snow);overflow:hidden";
    h1.style.cssText = "font:400 60px/1.05 var(--font-source-serif);letter-spacing:-.02em;text-align:left;margin:0";
    paper.style.cssText = "transform:scale(.78);transform-origin:left center;width:700px";
    card.append(h1, paper); document.body.append(card); document.querySelectorAll("nextjs-portal").forEach(n => n.remove());
  });
  await page.screenshot({ path: "public/brand/og-image.png" });
  await browser.close(); console.log("Saved public/brand/og-image.png");
}
void main();
