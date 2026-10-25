"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { motion, useInView, type Transition } from "motion/react";
import { Check } from "lucide-react";
import { stepperDemo as demo } from "@/lib/landing-data";
import { verdicts } from "./verdict-badge";
import { usePolishMotion } from "./landing-chrome";

const stages = [
  ["Parse", "Split the manuscript into sentences and citations."],
  ["Resolve", "Find each reference in Crossref, OpenAlex and arXiv."],
  ["Retraction", "Follow retraction findings back to the notice."],
  ["Sources", "Load the cited passage, full text or abstract."],
  ["Verify", "Compare the claim with a quote verified in the source."],
  ["Review", "Three reviewers and an area chair set priorities."],
] as const;
const ease = [.2, .7, .2, 1] as const;
// A demo plays once; until then (and after, with reduced motion) every element holds a still state.
type Play = { play: boolean; reduced: boolean };
const at = ({ play, reduced }: Play, delay = 0, duration = .22): Transition => play && !reduced ? { duration, delay, ease } : { duration: 0 };
const chipIn = (on: boolean) => on ? { opacity: 1, scale: [.9, 1.06, 1] } : { opacity: 0, scale: .9 };

function Swap({ on, t, from, to, tone }: { on: boolean; t: Transition; from: string; to: string; tone: string }) {
  return <span className="swap"><motion.span className="status-pill checking" initial={false} animate={{ opacity: on ? 0 : 1 }} transition={t}>{from}</motion.span><motion.span className={`status-pill ${tone}`} initial={false} animate={{ opacity: on ? 1 : 0, scale: on ? 1 : .96 }} transition={t}>{to}</motion.span></span>;
}

function Parse(p: Play) {
  return <ol className="demo-lines">{demo.parse.map((l, i) => <motion.li key={l.line} initial={false} animate={p.play ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }} transition={at(p, i * .35, .4)}><span className="demo-line-number">{String(l.line).padStart(2, "0")}</span>{l.text}</motion.li>)}</ol>;
}
function Resolve(p: Play) {
  return <ul className="demo-rows">{demo.resolve.map((r, i) => <li key={r.id}><span><strong>{r.byline}</strong><em>{r.title}</em></span><Swap on={p.play} t={at(p, .5 + i * .35, .2)} from="CHECKING" to={r.label} tone={r.tone} /></li>)}</ul>;
}
function Retraction(p: Play) {
  return <ul className="demo-rows">{demo.retraction.map((r, i) => <li key={r.id}><span><strong>{r.byline}</strong><em>{r.title}</em>{r.notice && <motion.a href={r.notice} target="_blank" rel="noreferrer" className="demo-notice" initial={false} animate={{ opacity: p.play ? 1 : 0 }} transition={at(p, 1.5, .3)}>Retraction notice ↗</motion.a>}</span>
    {r.retracted ? <motion.span className="demo-stamp" initial={false} animate={p.play ? { opacity: 1, scale: 1, rotate: -3 } : { opacity: 0, scale: 1.4, rotate: -8 }} transition={at(p, 1, .25)}>Retracted{r.year ? ` ${r.year}` : ""}</motion.span>
      : <motion.span className="status-pill sage" initial={false} animate={{ opacity: p.play ? 1 : 0 }} transition={at(p, .3 + i * .3, .3)}>No retraction found</motion.span>}</li>)}</ul>;
}
function Sources(p: Play) {
  const loaded = { opacity: p.play ? 1 : 0 };
  return <figure className="demo-source"><figcaption><span className="source-identifier">{demo.source.identifier}</span><span>{demo.source.level}</span></figcaption>
    <div className="demo-source-body">
      <motion.blockquote initial={false} animate={loaded} transition={at(p, 2.1, .4)}>{demo.source.passage ?? "Source text is unavailable. Needs review."}</motion.blockquote>
      <motion.div aria-hidden className="demo-skeleton" initial={false} animate={{ opacity: p.play ? 0 : 1 }} transition={at(p, 2, .25)}>{[92, 100, 84, 96, 60].map((w, i) => <span key={i} style={{ width: `${w}%` }}>{!p.reduced && <motion.i initial={{ x: "-100%" }} animate={p.play ? { x: "100%" } : { x: "-100%" }} transition={p.play ? { duration: .8, repeat: 2, ease: "linear" } : { duration: 0 }} />}</span>)}</motion.div>
    </div></figure>;
}
function Verify(p: Play) {
  const [glyph, label] = [demo.verify.verdict === "PARTIALLY_SUPPORTED" ? "◐" : demo.verify.verdict === "SUPPORTED" ? "✓" : "?", verdicts[demo.verify.verdict][0]];
  return <div className="demo-verify"><p className="demo-claim"><span>{demo.verify.claim}</span><motion.span aria-hidden className="demo-claim-sweep" initial={false} animate={{ clipPath: p.play ? "inset(0 0% 0 0)" : "inset(0 100% 0 0)" }} transition={at(p, .2, .9)}>{demo.verify.claim}</motion.span></p>
    <motion.blockquote initial={false} animate={p.play ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }} transition={at(p, 1.3, .4)}>“{demo.verify.quote ?? "No verified source quote available."}”</motion.blockquote>
    <motion.span className="hero-chip brass" initial={false} animate={chipIn(p.play)} transition={at(p, 1.9, .16)}><span aria-hidden>{glyph}</span> {label}</motion.span></div>;
}
function Review(p: Play) {
  const words = (demo.review.areaChair ?? "Area chair summary unavailable.").split(" ");
  return <div className="demo-review"><ul>{demo.review.panel.map((r, i) => <motion.li key={r.id} className="hero-chip blue" initial={false} animate={chipIn(p.play)} transition={at(p, .2 + i * .25, .16)}><strong>{r.id}</strong> {r.name} · {r.major} major{r.minor ? ` · ${r.minor} minor` : ""}</motion.li>)}</ul>
    <p className="demo-ac-label">Area chair · top priority</p>
    <p className="demo-ac"><span className="sr-only">{words.join(" ")}</span>{words.map((w, i) => <motion.span key={i} aria-hidden initial={false} animate={{ opacity: p.play ? 1 : 0 }} transition={at(p, .9 + i * .06, .1)}>{w} </motion.span>)}{!p.reduced && p.play && <motion.span aria-hidden className="demo-caret" initial={{ opacity: 1 }} animate={{ opacity: [1, 0, 1] }} transition={{ duration: .9, repeat: 3, delay: .9 + words.length * .06 }} />}</p></div>;
}
const demos = [Parse, Resolve, Retraction, Sources, Verify, Review];

function StageCard({ index, reduced, onCentre, children }: { index: number; reduced: boolean; onCentre: (i: number) => void; children: (p: Play) => ReactNode }) {
  const ref = useRef<HTMLElement>(null), seen = useInView(ref, { once: true, amount: .6 });
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) onCentre(index); }, { rootMargin: "-50% 0px -50% 0px" });
    observer.observe(ref.current!);
    return () => observer.disconnect();
  }, [index, onCentre]);
  return <article ref={ref} className="stage-card" data-stage-card={index + 1} aria-labelledby={`stage-${index + 1}`}><header><span>{String(index + 1).padStart(2, "0")}</span><h3 id={`stage-${index + 1}`}>{stages[index][0]}</h3></header>{children({ play: reduced || seen, reduced })}</article>;
}

export function LandingStepper() {
  const reduced = usePolishMotion(), [current, setCurrent] = useState(0);
  return <section id="how-it-works" className="article-section section-container stepper" aria-labelledby="stepper-title">
    <h2 id="stepper-title" className="editorial-title">Every citation, <strong>checked.</strong></h2>
    <div className="stepper-layout">
      <aside className="stepper-rail" aria-label="Review stages">
        <ol>{stages.map(([name, text], i) => <li key={name} aria-current={i === current ? "step" : undefined} data-complete={i < current}>
          <span className="rail-stop">{i < current ? <Check size={14} aria-hidden /> : String(i + 1).padStart(2, "0")}{i === current && !reduced && <motion.span aria-hidden className="rail-pulse" initial={{ scale: 1, opacity: .3 }} animate={{ scale: 2.8, opacity: 0 }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }} />}</span>
          <span><span className="rail-name">{name}{i === current && <span className="current-tag">Current stage</span>}</span><span className="rail-text">{text}</span></span></li>)}</ol>
        <div className="rail-segments" aria-hidden>{stages.map((_, i) => <span key={i}><motion.i initial={false} animate={{ scaleX: i <= current ? 1 : 0 }} transition={{ duration: reduced ? 0 : .22, ease }} /></span>)}</div>
        <p className="rail-progress">Stage {current + 1} of {stages.length}</p>
      </aside>
      <div className="stepper-cards">{demos.map((Demo, i) => <StageCard key={i} index={i} reduced={reduced} onCentre={setCurrent}>{p => <Demo {...p} />}</StageCard>)}</div>
    </div>
  </section>;
}
