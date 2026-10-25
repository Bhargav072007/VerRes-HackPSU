"use client";
import { useEffect, useRef } from "react";
import { cancelFrame, frame } from "motion/react";
import { usePolishMotion } from "./landing-chrome";
const GAP = 18, DOT = 1.5, RADIUS = 120;
// Dots near the pointer brighten and grow (lerped). Static on touch devices and with reduced motion.
export function DotMatrix() {
  const canvas = useRef<HTMLCanvasElement>(null), reduced = usePolishMotion();
  useEffect(() => {
    const node = canvas.current!, context = node.getContext("2d");
    if (!context) return;
    const live = !reduced && matchMedia("(hover: hover) and (pointer: fine)").matches;
    let width = 0, height = 0, cols = 0, rows = 0, level = new Float32Array(0), running = false;
    const pointer = { x: -1e4, y: -1e4 };
    const draw = () => {
      let moving = false;
      context.clearRect(0, 0, width, height);
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const i = r * cols + c, x = GAP / 2 + c * GAP, y = GAP / 2 + r * GAP, d = Math.hypot(x - pointer.x, y - pointer.y);
        const target = d < RADIUS ? (1 - d / RADIUS) ** 2 : 0, next = level[i] + (target - level[i]) * .14;
        level[i] = Math.abs(target - next) < .002 ? target : next;
        if (level[i] !== target) moving = true;
        context.fillStyle = `rgba(237,235,230,${.2 + .75 * level[i]})`;
        context.beginPath(); context.arc(x, y, (DOT / 2) * (1 + 1.6 * level[i]), 0, Math.PI * 2); context.fill();
      }
      return moving;
    };
    const tick = () => { if (!draw()) stop(); };
    const start = () => { if (live && !running) { running = true; frame.render(tick, true); } };
    const stop = () => { running = false; cancelFrame(tick); };
    const resize = () => {
      const box = node.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
      width = box.width; height = box.height; cols = Math.ceil(width / GAP); rows = Math.ceil(height / GAP); level = new Float32Array(cols * rows);
      node.width = Math.round(width * dpr); node.height = Math.round(height * dpr); context.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    };
    const move = (e: PointerEvent) => { if (e.pointerType !== "mouse") return; const box = node.getBoundingClientRect(); pointer.x = e.clientX - box.left; pointer.y = e.clientY - box.top; start(); };
    const leave = () => { pointer.x = pointer.y = -1e4; start(); };
    const observer = new ResizeObserver(resize);
    observer.observe(node);
    if (live) { node.addEventListener("pointermove", move); node.addEventListener("pointerleave", leave); }
    return () => { observer.disconnect(); stop(); node.removeEventListener("pointermove", move); node.removeEventListener("pointerleave", leave); };
  }, [reduced]);
  return <figure className="dot-matrix"><canvas ref={canvas} aria-hidden /><figcaption>Move through it.</figcaption></figure>;
}
