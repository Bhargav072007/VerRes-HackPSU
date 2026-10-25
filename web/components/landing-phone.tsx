"use client";
import { useRef } from "react";
import { motion, useMotionTemplate, useScroll, useTransform } from "motion/react";
import { useSceneReducedMotion } from "./landing-chrome";
import { MockupImage } from "./mockup-image";
// Scroll-linked focus: the photo sharpens as it enters, holds while centred, and softens as it leaves.
const stops = [0, .35, .65, 1];
export function LandingPhone() {
 const section = useRef<HTMLElement>(null), reduced = useSceneReducedMotion();
 const { scrollYProgress } = useScroll({ target: section, offset: ["start end", "end start"] });
 const blur = useTransform(scrollYProgress, stops, reduced ? [0, 0, 0, 0] : [14, 0, 0, 10]);
 const opacity = useTransform(scrollYProgress, stops, reduced ? [1, 1, 1, 1] : [.35, 1, 1, .4]);
 const scale = useTransform(scrollYProgress, stops, reduced ? [1, 1, 1, 1] : [1.06, 1, 1, .98]);
 const y = useTransform(scrollYProgress, [0, 1], reduced ? [0, 0] : [24, -24]);
 const filter = useMotionTemplate`blur(${blur}px)`;
 return <section ref={section} id="anywhere" className="phone-moment section-container" aria-labelledby="phone-title">
  <div className="phone-copy"><h2 id="phone-title" className="editorial-title">The same evidence, <strong>wherever you read.</strong></h2><p>A reference can exist without supporting the sentence that cites it. Inspect the claim beside the passage, then follow its source.</p></div>
  <motion.div className="phone-focus" style={{ y, scale, opacity, filter }}>
   <MockupImage scene="iphone-report" reveal={false} sizes="(max-width: 700px) 90vw, 50vw" alt="The BERT finding and its inline reviewer note in a VerRes report on a phone, over an open journal" />
  </motion.div>
 </section>;
}
