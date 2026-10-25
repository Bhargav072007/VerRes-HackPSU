"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowDown, ArrowRight, FileText } from "lucide-react";
import NumberFlow from "@number-flow/react";
import { usePolishMotion } from "./landing-chrome";
import { counterTiming } from "@/lib/motion";

const references = [
  ["Learning from limited data", "A. Chen et al.", "2023"], ["Attention and representation", "M. Patel et al.", "2021"],
  ["Rethinking model evaluation", "J. Rivera et al.", "2024"], ["A study of transfer learning", "S. Kim et al.", "2020"],
  ["Beyond the benchmark", "L. Morgan et al.", "2022"], ["Measuring what matters", "R. Okafor et al.", "2023"],
  ["The limits of generalization", "E. Park et al.", "2019"], ["Evidence in machine learning", "N. Singh et al.", "2024"],
  ["A reproducible baseline", "D. Costa et al.", "2022"], ["On robust representations", "H. Wilson et al.", "2021"],
  ["Data, methods, and meaning", "I. Ahmed et al.", "2020"], ["Toward reliable inference", "C. Lee et al.", "2024"],
];
const verdicts = [["✓", "Supported", "sage"], ["◐", "Partial", "brass"], ["✕", "Retracted", "red"], ["?", "Needs review", "blue"]];

export function LandingScene() {
  const scene = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = scene.current;
    if (!node) return;
    const media = matchMedia("(min-width: 1000px) and (prefers-reduced-motion: no-preference)");
    let frame = 0;
    const update = () => {
      frame = 0;
      const enabled = media.matches && document.documentElement.dataset.a11yMotion !== "reduce";
      node.toggleAttribute("data-static", !enabled);
      const rect = node.getBoundingClientRect();
      const p = enabled ? Math.min(1, Math.max(0, -rect.top / (rect.height - innerHeight))) : 0;
      node.style.setProperty("--scene", String(p));
      node.querySelectorAll<HTMLElement>(".floating-reference").forEach((card, i) => {
        const t = Math.min(1, Math.max(0, (p - i * .018) / .7));
        const x = (i % 2 ? 1 : -1) * Math.min(540, innerWidth * .36);
        const y = 110 + Math.floor(i / 2) * 100;
        card.style.transform = enabled ? `translate3d(${x * (1 - t)}px,${y * (1 - t) + 570 * t}px,0) rotate(${(i % 3 - 1) * 4 * (1 - t)}deg) scale(${1 - .7 * t})` : "";
        card.style.opacity = enabled ? String(1 - t) : "";
      });
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    addEventListener("scroll", schedule, { passive: true }); addEventListener("resize", schedule); media.addEventListener("change", schedule);
    const observer = new MutationObserver(schedule); observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-a11y-motion"] });
    update();
    return () => { cancelAnimationFrame(frame); removeEventListener("scroll", schedule); removeEventListener("resize", schedule); media.removeEventListener("change", schedule); observer.disconnect(); };
  }, []);
  return <section ref={scene} className="hero-scene" aria-labelledby="headline"><div className="hero-stage">
    <div className="hero-copy"><p className="beta-note"><span>Open beta</span> A little scrutiny. A stronger paper.</p><h1 id="headline" aria-label="Proof, not vibes."><span className="line-mask"><span data-reveal><mark>Proof</mark>,</span></span><span className="line-mask"><span data-reveal>not vibes.</span></span></h1><p className="hero-lead">A pre-submission integrity review for research papers.</p><div className="hero-actions"><a className="pill-button" href="#submit">Review your paper <ArrowRight size={15} /></a><a className="outline-button" href="#how-it-works">See what we check</a></div><p className="scroll-caption"><ArrowDown size={12} /> Scroll. Twelve references become one report.</p></div>
    <div className="reference-cloud" aria-label="Twelve illustrative references">{references.map(([title, author, year], i) => <article className="floating-reference" key={title}><div className="source-card crosshair" style={{ "--i": i } as CSSProperties}><span className="source-icon"><FileText size={16} strokeWidth={1.3} /></span><div><p className="eyebrow">REFERENCE · {String(i + 1).padStart(2, "0")}</p><h2>{title}</h2><p className="source-author">{author} · {year}</p></div></div></article>)}</div>
    <article className="mock-report crosshair" aria-label="Illustrative report"><div className="report-toolbar"><span>VERRES / INTEGRITY REVIEW</span><span>ILLUSTRATIVE DEMO</span></div><div className="report-page"><p className="eyebrow">EVERY FINDING HAS A RECEIPT</p><h2>A closer look at the evidence.</h2><p className="reading-text">A citation is only the beginning. Follow it to the source, inspect the passage, and see whether the evidence supports the claim.</p><div className="demo-finding"><span className="status-pill sage">✓ Supported</span><p>Claim linked to a matching source passage.</p><span className="eyebrow">SOURCE PASSAGE → CLAIM → VERDICT</span></div><p className="eyebrow">12 REFERENCES · EXAMPLE VERDICTS</p><div className="demo-chips">{references.map(([title], i) => { const [icon, label, tone] = verdicts[i % 4]; return <span className={`status-pill ${tone}`} key={title} style={{ "--i": i } as CSSProperties}>{icon} {i + 1} · {label}</span>; })}</div><p className="demo-disclaimer">Fictional references and findings. A preview of the format, not a real review.</p></div></article>
  </div></section>;
}

export function DemoStats() {
  const node = useRef<HTMLDivElement>(null);
  const [counted, setCounted] = useState(false);
  const reduced = usePolishMotion();
  useEffect(() => {
    const observer = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) { setCounted(true); observer.disconnect(); } });
    if (node.current) observer.observe(node.current);
    return () => observer.disconnect();
  }, []);
  return <div ref={node} className="stat-band crosshair" aria-label="Illustrative report statistics">{[[12, "references", ""], [8, "verified quotes", ""], [4, "flags to inspect", ""], [42, "elapsed time", "s"]].map(([value, label, suffix]) => <div key={String(label)}><strong><NumberFlow value={counted ? Number(value) : 0} suffix={String(suffix)} animated={!reduced} trend={1} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={counterTiming} /></strong><span>{label}</span></div>)}<p>Illustrative report only. These figures are not a performance benchmark.</p></div>;
}
