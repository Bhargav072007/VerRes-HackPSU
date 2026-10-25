// node scripts/d17/convert-iphone.mjs [../iPhone.tiff] — the source TIFF is never committed.
import sharp from "sharp";
import { readFile, writeFile } from "node:fs/promises";
const source = process.argv[2] || "../iPhone.tiff", out = "public/mockups/iphone-report";
const { width, height } = await sharp(source).metadata();
await sharp(source).avif({ quality: 60, effort: 6 }).toFile(`${out}@2x.avif`);
await sharp(source).resize({ width: Math.round(width / 2) }).avif({ quality: 60, effort: 6 }).toFile(`${out}@1x.avif`);
await sharp(source).webp({ quality: 82 }).toFile(`${out}.webp`);
const blur = await sharp(source).resize({ width: 12 }).webp({ quality: 50 }).toBuffer();
const manifest = JSON.parse(await readFile("public/mockups/manifest.json", "utf8"));
manifest["iphone-report"] = { width, height, blurDataURL: `data:image/webp;base64,${blur.toString("base64")}` };
await writeFile("public/mockups/manifest.json", JSON.stringify(manifest, null, 2) + "\n");
console.log(`iphone-report ${width}x${height}`);
