"use client";
import { useState } from "react";
import { motion, useSpring } from "motion/react";
import { usePolishMotion } from "./landing-chrome";
// The logo mark beside the footer lockup: tilts toward the pointer (spring, ±8°), sweeps a sheen across the ribbon on hover or focus, and returns to the top.
export function FooterMark() {
  const reduced = usePolishMotion(), rotateX = useSpring(0, { stiffness: 220, damping: 18 }), rotateY = useSpring(0, { stiffness: 220, damping: 18 });
  const [sweeps, setSweeps] = useState(0);
  const sheen = () => { if (!reduced) setSweeps(n => n + 1); };
  return <motion.button type="button" className="footer-mark" aria-label="Back to top" style={{ rotateX, rotateY }}
    onPointerEnter={sheen} onFocus={sheen}
    onPointerMove={e => { if (reduced || e.pointerType !== "mouse") return; const box = e.currentTarget.getBoundingClientRect(); rotateY.set(((e.clientX - box.left) / box.width - .5) * 16); rotateX.set(-((e.clientY - box.top) / box.height - .5) * 16); }}
    onPointerLeave={() => { rotateX.set(0); rotateY.set(0); }}
    onClick={() => scrollTo({ top: 0, behavior: reduced ? "instant" : "smooth" })}>
    <span className="footer-mark-logo" aria-hidden />
    <span className="footer-mark-clip" aria-hidden>{sweeps > 0 && <motion.span key={sweeps} className="footer-mark-sheen" initial={{ x: "-120%" }} animate={{ x: "120%" }} transition={{ duration: .9, ease: [.2, .7, .2, 1] }} />}</span>
  </motion.button>;
}
