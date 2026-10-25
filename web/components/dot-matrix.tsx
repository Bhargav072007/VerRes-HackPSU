"use client";
import { useEffect, useRef } from "react";
import { cancelFrame, frame } from "motion/react";
import { usePolishMotion } from "./landing-chrome";
const GAP = 6, DOT = 2.2, PUSH = 90, INTRO = 1100, BURST = 700;
type Dot = { hx: number; hy: number; x: number; y: number; fx: number; fy: number; delay: number; glow: number; r: number; g: number; b: number };
const easeOut = (t: number) => 1 - (1 - t) ** 3;
// The VerRes mark rebuilt from dots coloured by the logo pixel beneath each one. Dots assemble when the section is 40% visible,
// shy away from the pointer and spring back, and burst then reassemble on click or tap. Static with reduced motion.
export function DotMatrix() {
  const canvas = useRef<HTMLCanvasElement>(null), reduced = usePolishMotion();
  useEffect(() => {
    const node = canvas.current!, context = node.getContext("2d");
    if (!context) return;
    const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
    let dots: Dot[] = [], width = 0, height = 0, running = false, visible = false, started = false, tween: { start: number; length: number; stagger: boolean } | null = null;
    const pointer = { x: -1e4, y: -1e4 }, logo = new Image();
    const draw = (now: number) => {
      let moving = false;
      context.clearRect(0, 0, width, height);
      const t = tween && (now - tween.start) / tween.length;
      for (const d of dots) {
        let alpha = 1;
        if (tween) {
          const local = tween.stagger ? Math.min(1, Math.max(0, ((now - tween.start) - d.delay * 400) / (tween.length - 400))) : Math.min(1, t!), e = easeOut(local);
          d.x = d.fx + (d.hx - d.fx) * e; d.y = d.fy + (d.hy - d.fy) * e; alpha = tween.stagger ? e : 1;
          if (local < 1) moving = true;
        } else {
          const dx = d.hx - pointer.x, dy = d.hy - pointer.y, dist = Math.hypot(dx, dy), near = dist < PUSH ? 1 - dist / PUSH : 0;
          const tx = d.hx + (dist ? dx / dist : 0) * near * 26, ty = d.hy + (dist ? dy / dist : 0) * near * 26;
          d.x += (tx - d.x) * .12; d.y += (ty - d.y) * .12; d.glow += (near - d.glow) * .12;
          if (Math.abs(tx - d.x) > .05 || Math.abs(ty - d.y) > .05 || Math.abs(near - d.glow) > .005) moving = true;
        }
        const lift = d.glow * 60;
        context.fillStyle = `rgba(${Math.min(255, d.r + lift)},${Math.min(255, d.g + lift)},${Math.min(255, d.b + lift)},${alpha})`;
        context.beginPath(); context.arc(d.x, d.y, DOT / 2 * (1 + d.glow * .5), 0, Math.PI * 2); context.fill();
      }
      if (tween && !moving) { tween = null; node.dataset.state = "assembled"; moving = true; }
      return moving;
    };
    const tick = () => { if (!draw(performance.now())) stop(); };
    const start = () => { if (!running && visible) { running = true; frame.render(tick, true); } };
    const stop = () => { running = false; cancelFrame(tick); };
    const scatter = (burst: boolean) => {
      for (const d of dots) {
        const angle = burst ? Math.atan2(d.hy - height / 2, d.hx - width / 2) : 0, reach = 60 + Math.random() * 90;
        d.fx = burst ? d.x + Math.cos(angle) * reach : Math.random() * width; d.fy = burst ? d.y + Math.sin(angle) * reach : Math.random() * height;
      }
      tween = { start: performance.now(), length: burst ? BURST : INTRO, stagger: !burst };
      node.dataset.state = burst ? "burst" : "assembling"; start();
    };
    const build = () => {
      const box = node.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
      width = box.width; height = box.height; node.width = Math.round(width * dpr); node.height = Math.round(height * dpr); context.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!logo.complete || !logo.naturalWidth) return;
      // The vector mark is rasterised once at 600px wide, then fitted into the canvas for sampling.
      const raster = document.createElement("canvas"), aspect = logo.naturalHeight / logo.naturalWidth || .55;
      raster.width = 600; raster.height = Math.round(600 * aspect); raster.getContext("2d")!.drawImage(logo, 0, 0, raster.width, raster.height);
      const fitW = Math.min(width * .82, height * .82 / aspect), left = (width - fitW) / 2, top = (height - fitW * aspect) / 2, sample = document.createElement("canvas");
      sample.width = Math.round(fitW); sample.height = Math.round(fitW * aspect);
      const sctx = sample.getContext("2d", { willReadFrequently: true })!;
      sctx.drawImage(raster, 0, 0, sample.width, sample.height);
      const pixels = sctx.getImageData(0, 0, sample.width, sample.height).data;
      dots = [];
      for (let y = GAP / 2; y < sample.height; y += GAP) for (let x = GAP / 2; x < sample.width; x += GAP) {
        const i = (Math.floor(y) * sample.width + Math.floor(x)) * 4;
        if (pixels[i + 3] <= 127) continue;
        const hx = left + x, hy = top + y;
        dots.push({ hx, hy, x: hx, y: hy, fx: hx, fy: hy, delay: Math.hypot(hx - width / 2, hy - height / 2), glow: 0, r: pixels[i], g: pixels[i + 1], b: pixels[i + 2] });
      }
      // Stagger by distance from the centre, normalised to the farthest dot.
      const farthest = Math.max(1, ...dots.map(d => d.delay));
      for (const d of dots) d.delay /= farthest;
      // Before the intro the canvas stays empty; with reduced motion (or after the intro) the logo is drawn assembled.
      if (reduced || started) { node.dataset.state = "assembled"; draw(performance.now()); }
      else { node.dataset.state = "scattered"; context.clearRect(0, 0, width, height); }
    };
    const move = (e: PointerEvent) => { if (e.pointerType !== "mouse" || tween) return; const box = node.getBoundingClientRect(); pointer.x = e.clientX - box.left; pointer.y = e.clientY - box.top; start(); };
    const leave = () => { pointer.x = pointer.y = -1e4; start(); };
    const click = () => { if (started && !tween) scatter(true); };
    const resizer = new ResizeObserver(() => { build(); if (started && !reduced) start(); });
    const viewer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && entry.intersectionRatio >= .4 && !started && !reduced && dots.length) { started = true; scatter(false); }
      if (visible) start(); else stop();
    }, { threshold: [0, .4] });
    logo.onload = () => { build(); viewer.observe(node); };
    logo.src = "/brand/verres-mark.svg";
    resizer.observe(node);
    if (!reduced) { node.addEventListener("click", click); if (fine) { node.addEventListener("pointermove", move); node.addEventListener("pointerleave", leave); } }
    return () => { resizer.disconnect(); viewer.disconnect(); stop(); node.removeEventListener("click", click); node.removeEventListener("pointermove", move); node.removeEventListener("pointerleave", leave); };
  }, [reduced]);
  return <figure className="dot-matrix dot-logo"><canvas ref={canvas} aria-hidden /><figcaption>Move through it.</figcaption></figure>;
}
