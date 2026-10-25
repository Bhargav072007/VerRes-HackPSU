"use client";
import { useRef } from "react";
import { motion, useScroll, useTransform } from "motion/react";
import { useSceneReducedMotion } from "./landing-chrome";
import { MockupImage } from "./mockup-image";
export function LandingPhone() {
 const section = useRef<HTMLElement>(null), reduced = useSceneReducedMotion();
 const { scrollYProgress } = useScroll({ target: section, offset: ["start end", "end start"] });
 const parallax = useTransform(scrollYProgress, [0, 1], reduced ? [0, 0] : [20, -20]);
 return <section ref={section} id="anywhere" className="phone-moment section-container" aria-labelledby="phone-title">
  <div className="phone-copy"><h2 id="phone-title" className="editorial-title">The same evidence, <strong>wherever you read.</strong></h2><p>A reference can exist without supporting the sentence that cites it. Inspect the claim beside the passage, then follow its source.</p></div>
  <motion.div className="phone-parallax" style={{ y: parallax }}><motion.div className="phone-rise" initial={{ y: 40, scale: .96 }} animate={reduced ? { y: 0, scale: 1 } : undefined} whileInView={{ y: 0, scale: 1 }} viewport={{ once: true, amount: .25 }} transition={{ duration: reduced ? 0 : .5, ease: [.2, .7, .2, 1] }}>
   <MockupImage scene="s2" reveal={false} sizes="(max-width: 700px) 90vw, 45vw" alt="The BERT finding and inline reviewer note on a phone" />
  </motion.div></motion.div>
 </section>;
}
