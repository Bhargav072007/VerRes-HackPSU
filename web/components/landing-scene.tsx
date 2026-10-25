"use client";
import { useEffect, useRef } from "react";
import { ArrowDown, ArrowRight } from "lucide-react";
import { usePolishMotion } from "./landing-chrome";
import { ManuscriptSequence } from "./manuscript-sequence";
export function LandingScene() {
  const reduced = usePolishMotion();
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (reduced) return;
    let active = true;
    let dispose: (() => void) | undefined;
    void import("lenis").then(({ default: Lenis }) => {
      if (!active) return;
      const lenis = new Lenis({ autoRaf: true, duration: .35, anchors: true, smoothWheel: true });
      document.documentElement.dataset.landingScroll = "smooth";
      dispose = () => { lenis.destroy(); delete document.documentElement.dataset.landingScroll; };
    });
    return () => { active = false; dispose?.(); };
  }, [reduced]);
  return <div ref={container}><ManuscriptSequence><div className="article-hero-copy"><p className="article-kicker">A pre-submission review</p><h1 id="headline" aria-label="Read your paper like Reviewer 2 would."><span className="line-mask"><span data-reveal>Read your paper</span></span><span className="line-mask"><span data-reveal>like <em>Reviewer 2</em></span></span><span className="line-mask"><span data-reveal>would.</span></span></h1><p className="article-lead">VerRes checks every reference in your manuscript, finds the passage you cited, and flags where a claim goes further than its source — before anyone else does.</p><div className="hero-actions"><a className="pill-button" href="#submit">Review your paper <ArrowRight size={15} /></a><a className="outline-button" href="#results">See a sample report</a></div><p className="article-tagline">Every finding links to its evidence.</p><p className="scroll-caption"><ArrowDown size={12} /> Follow a paper through review</p></div></ManuscriptSequence></div>;
}
