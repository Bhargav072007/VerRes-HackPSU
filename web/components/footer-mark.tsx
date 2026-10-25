"use client";
import { useState } from "react";
import { motion, useSpring } from "motion/react";
import { usePolishMotion } from "./landing-chrome";
// The VerRes mark as a "Back to top" button. A sheen sweeps across the ribbon on hover, on focus and whenever `sheenKey` changes;
// with `tilt`, it also leans toward the pointer (spring, ±8°).
export function LogoMarkButton({ className, sheenKey, tilt = false, hidden = false }: { className: string; sheenKey?: string; tilt?: boolean; hidden?: boolean }) {
  const reduced = usePolishMotion(), rotateX = useSpring(0, { stiffness: 220, damping: 18 }), rotateY = useSpring(0, { stiffness: 220, damping: 18 });
  const [sweeps, setSweeps] = useState(0);
  const sheen = () => { if (!reduced) setSweeps(n => n + 1); };
  // Keyed on the section and the hover count, so either change replays the sweep once.
  const sweepKey = `${sheenKey ?? ""}:${sweeps}`, sweeping = !reduced && (sweeps > 0 || sheenKey !== undefined);
  return <motion.button type="button" className={`logo-mark ${className}`} aria-label="Back to top" inert={hidden} style={tilt ? { rotateX, rotateY } : undefined}
    onPointerEnter={sheen} onFocus={sheen}
    onPointerMove={e => { if (!tilt || reduced || e.pointerType !== "mouse") return; const box = e.currentTarget.getBoundingClientRect(); rotateY.set(((e.clientX - box.left) / box.width - .5) * 16); rotateX.set(-((e.clientY - box.top) / box.height - .5) * 16); }}
    onPointerLeave={() => { rotateX.set(0); rotateY.set(0); }}
    onClick={() => scrollTo({ top: 0, behavior: reduced ? "instant" : "smooth" })}>
    <span className="logo-mark-art" aria-hidden />
    <span className="logo-mark-clip" aria-hidden>{sweeping && <motion.span key={sweepKey} className="logo-mark-sheen" initial={{ x: "-120%" }} animate={{ x: "120%" }} transition={{ duration: .9, ease: [.2, .7, .2, 1] }} />}</span>
  </motion.button>;
}
export function FooterMark() { return <LogoMarkButton className="footer-mark" tilt />; }
