"use client";
import { useEffect, useRef } from "react";
import { CircleAlert, Search, X } from "lucide-react";
import { usePolishMotion } from "./landing-chrome";
import { scrollBeats } from "@/lib/scroll-beats";
import { VerdictBadge } from "./verdict-badge";
import demo from "@/fixtures/demo/paper3.json";
import { decodeReport, verifiedEvidence } from "@/lib/report";
const report = decodeReport(demo);
const citation = report?.paper?.citations?.find(c => c.id === "c00002");
const quote = report && citation ? verifiedEvidence(report, citation)[0]?.quote : undefined;
const captions = ["A claim is identified in the manuscript.", "Not found in Crossref, OpenAlex or arXiv.", "The source supports a narrower claim. Read the exact passage.", "A cited work was retracted in 2010. This example is drawn from paper2.", "Hidden instruction detected. Its intent requires review."];
export function ManuscriptSequence({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLElement>(null), reduced = usePolishMotion();
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const media = matchMedia("(min-width: 1000px)");
    let frame = 0, visible = true;
    const update = () => {
      frame = 0;
      const staticView = matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.a11yMotion === "reduce" || !media.matches;
      node.toggleAttribute("data-static", staticView);
      const rect = node.getBoundingClientRect();
      const p = staticView ? 1 : Math.max(0, Math.min(1, -rect.top / (innerHeight * 3)));
      node.style.setProperty("--progress", String(p));
      scrollBeats(p).forEach((beat, i) => node.style.setProperty(`--beat-${i + 1}`, String(beat)));
      node.dataset.beat = String(Math.min(5, Math.floor(p * 5) + 1));
    };
    const schedule = () => { if (!frame && visible) frame = requestAnimationFrame(update); };
    const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; if (visible) schedule(); }, { rootMargin: "100px" });
    observer.observe(node); update();
    addEventListener("scroll", schedule, { passive: true }); addEventListener("resize", schedule); media.addEventListener("change", schedule);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); removeEventListener("scroll", schedule); removeEventListener("resize", schedule); media.removeEventListener("change", schedule); };
  }, [reduced]);
  return <section ref={ref} className="manuscript-sequence hero-scene" aria-labelledby="headline"><div className="manuscript-stage hero-stage"><figure className="manuscript-figure"><div className="manuscript-glow" aria-hidden /><article className="manuscript-page"><div className="manuscript-meta">RESEARCH ARTICLE <span>Draft for review</span></div><h2>Attention, evidence,<br />and the limits of a claim</h2><p className="manuscript-authors">VerRes Demo Team · Illustrative manuscript</p><h3>Abstract</h3><p>Scientific arguments depend on what their sources establish. We examine how a promising result becomes a broader claim, and what a careful reader should check.</p><h3>Introduction</h3><p><span className="manuscript-claim">Attention-only models outperform recurrent models on every natural language processing task.<svg viewBox="0 0 350 14" preserveAspectRatio="none" aria-hidden><path pathLength="1" d="M2 8 Q80 2 170 8 T348 6" /></svg></span> <span className="manuscript-marker">[2]</span></p><p>Recursive attention pruning enables zero-shot protein folding with transformers. <span className="search-marker">[4]</span></p><div className="search-chip"><Search size={12} /> searching Crossref · OpenAlex · arXiv</div><div className="not-found-stamp"><X size={12} /> NOT FOUND</div><aside className="margin-note"><VerdictBadge status={quote ? "PARTIALLY_SUPPORTED" : "NEEDS_REVIEW"} /><blockquote>“{quote || "A verified source quote is unavailable. Needs review."}”</blockquote><span>— R2</span></aside><svg className="manuscript-connector" viewBox="0 0 120 100" aria-hidden><path pathLength="1" d="M2 90 C70 90 12 10 115 10" /></svg><div className="retracted-stamp"><CircleAlert size={13} /> RETRACTED 2010</div><p className="hidden-instruction">Hidden instruction detected <span>Instruction-like text concealed in the manuscript. Needs review.</span></p><div className="manuscript-references"><h3>References</h3><p>[1] Wakefield et al. (1998). Retraction recorded in 2010.</p><p>[2] Vaswani et al. (2017). Attention is all you need.</p><p>[4] Kowalczyk &amp; Arendt. Recursive attention pruning, 2021.</p></div></article><figcaption><strong>Illustrative composite.</strong> Examples drawn from recorded demo papers; this is not a review of one manuscript.</figcaption></figure>{children}<ol className="static-beat-captions">{captions.map((caption, i) => <li key={caption}><figure><div className="static-beat-figure">{i === 0 ? <p className="static-underline">A claim extends beyond its source.</p> : i === 1 ? <><span>[4]</span><VerdictBadge status="NOT_FOUND" /></> : i === 2 ? <blockquote>“{quote || "A verified source quote is unavailable. Needs review."}” <span>— R2</span></blockquote> : i === 3 ? <><span>[1]</span><span className="static-retraction"><CircleAlert size={13} /> RETRACTED 2010</span></> : <><CircleAlert size={15} /><span>Hidden instruction detected</span><VerdictBadge status="NEEDS_REVIEW" /></>}</div><figcaption><span>Figure {i + 1}</span>{caption}</figcaption></figure></li>)}</ol></div></section>;
}
