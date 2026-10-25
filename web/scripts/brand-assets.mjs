import sharp from 'sharp';
import { mkdir, writeFile } from 'node:fs/promises';
const source = new URL('../../design-ref/brand/verres-logo.png', import.meta.url);
const target = new URL('../public/brand/', import.meta.url);
await mkdir(target, { recursive: true });
const lockup = await sharp(source.pathname).trim({ threshold: 8 }).resize({ width: 300 }).png().toBuffer();
await writeFile(new URL('verres-lockup.png', target), lockup);
const mark = await sharp(await sharp(source.pathname).extract({ left: 220, top: 85, width: 1180, height: 650 }).toBuffer()).trim({ threshold: 8 }).png().toBuffer();
for (const [name, size] of [['verres-mark', 56], ['icon-192', 192], ['icon-512', 512], ['apple-touch-icon', 180]]) {
  await sharp(mark).resize(size, size, { fit: 'contain', background: '#00000000' }).png().toFile(new URL(`${name}.png`, target).pathname);
}
const png = await sharp(mark).resize(32, 32, { fit: 'contain', background: '#00000000' }).png().toBuffer();
const header = Buffer.alloc(22); header.writeUInt16LE(1, 2); header.writeUInt16LE(1, 4); header[6] = 32; header[7] = 32; header.writeUInt16LE(1, 10); header.writeUInt16LE(32, 12); header.writeUInt32LE(png.length, 14); header.writeUInt32LE(22, 18);
await writeFile(new URL('../app/favicon.ico', import.meta.url), Buffer.concat([header, png]));
const type = Buffer.from(`<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg"><rect width="1200" height="630" fill="#f6f6f5"/><text x="100" y="350" font-family="sans-serif" font-size="60" fill="#1b1b19" letter-spacing="-2">Read your paper like</text><text x="100" y="425" font-family="sans-serif" font-size="60" fill="#1b1b19" letter-spacing="-2">Reviewer 2 would.</text><text x="104" y="520" font-family="sans-serif" font-size="23" fill="#5c5b57">Every finding links to its evidence.</text></svg>`);
await sharp(type).composite([{ input: await sharp(mark).resize(140, 100, { fit: 'inside' }).toBuffer(), left: 100, top: 95 }]).png().toFile(new URL('og-image.png', target).pathname);
// The old generated SVG icon must not override the ribbon favicon.
const { unlink } = await import('node:fs/promises');
await unlink(new URL('../app/icon.svg', import.meta.url)).catch(error => { if (error.code !== 'ENOENT') throw error; });
