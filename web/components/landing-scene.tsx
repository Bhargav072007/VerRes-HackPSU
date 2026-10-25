"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, type MotionStyle, useInView, useMotionValueEvent, useScroll, useTransform, type MotionValue } from "motion/react";
import { Ban, CircleCheck, CircleDashed, CircleHelp, CircleX, Link2Off, SearchX, type LucideIcon } from "lucide-react";
import { countWord, findingStyles, heroCards, heroPaper, heroTally, type HeroChip } from "@/lib/landing-data";
import { useMediaQuery, useSceneReducedMotion } from "./landing-chrome";

const icons: Record<HeroChip, LucideIcon> = { SUPPORTED: CircleCheck, PARTIALLY_SUPPORTED: CircleDashed, NOT_SUPPORTED: CircleX, CONTRADICTED: CircleX, NOT_FOUND: SearchX, DOI_MISMATCH: Link2Off, RETRACTED: Ban, NEEDS_REVIEW: CircleHelp };
// Resting slots around the headline: [side, inset %, top %, rotation°]. Landing order interleaves left and right.
const slots = [["left", 2.5, 9, -4], ["right", 3, 7, 3.5], ["left", 9, 33, 2.5], ["right", 9.5, 31, -3], ["left", 1.5, 56, -2], ["right", 2, 54, 4], ["left", 10, 76, 3], ["right", 11, 77, -2.5]] as const;
const order = [3, 0, 6, 1, 5, 2, 7, 4];
const FLIGHT = { start: .2, stagger: .07, length: .22 };
const RISE_END = .3;
const landAt = (rank: number) => FLIGHT.start + rank * FLIGHT.stagger + FLIGHT.length;
const landedBy = (p: number) => order.filter((_, rank) => p >= landAt(rank)).length;
const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
// Gravity-like easing, cubic-bezier(.55,0,.1,1), solved for y at x = t.
function gravity(t: number) {
  const bez = (a: number, b: number, s: number) => 3 * a * s * (1 - s) ** 2 + 3 * b * s * s * (1 - s) + s ** 3;
  let lo = 0, hi = 1, s = t;
  for (let i = 0; i < 18; i++) { s = (lo + hi) / 2; if (bez(.55, .1, s) < t) lo = s; else hi = s; }
  return bez(0, 1, s);
}

function Finding({ chip, children }: { chip: HeroChip; children?: React.ReactNode }) {
  const { label, color, text } = findingStyles[chip], Icon = icons[chip];
  return <span className="finding-label" style={{ color: text }}><Icon size={15} aria-hidden style={{ color }} />{label}{children}</span>;
}

type Target = { dx: number; dy: number; scale: number };
function HeroCard({ index, progress, target, reduced }: { index: number; progress: MotionValue<number>; target?: Target; reduced: boolean }) {
  const card = heroCards[index], [side, inset, top, rotation] = slots[index], rank = order.indexOf(index), start = FLIGHT.start + rank * FLIGHT.stagger;
  const transform = useTransform(progress, p => {
    const t = clamp01((p - start) / FLIGHT.length), e = gravity(t), dx = target?.dx ?? 0, dy = target?.dy ?? 0;
    // Curve: drift sideways early, fall late (gravity), so the path bows outward before dropping into the slot.
    const x = dx * (1 - (1 - e) ** 2), y = dy * e * e - 60 * Math.sin(Math.PI * e) * (dy > 0 ? 1 : -1);
    return `translate3d(${x}px,${y}px,0) rotate(${rotation * (1 - e)}deg) scale(${1 + ((target?.scale ?? 1) - 1) * e})`;
  });
  const opacity = useTransform(progress, p => { const t = clamp01((p - start) / FLIGHT.length); return t < .85 ? 1 : 1 - (t - .85) / .15; });
  const style = findingStyles[card.chip];
  return <li className="hero-card-slot" style={{ [side]: `${inset}%`, top: `${top}%` }}>
    <motion.div className="hero-card-flight" style={{ transform, opacity }}>
      <motion.article className="hero-card" style={{ borderLeftColor: style.color }} initial={false} animate={reduced ? { y: 0, rotate: 0 } : { y: [0, 6, -6, 0], rotate: [0, .7, -.7, 0] }} transition={reduced ? { duration: 0 } : { duration: 6 + (index % 4), repeat: Infinity, ease: "easeInOut", delay: index * .35 }}>
        <Finding chip={card.chip} />
        <p className="hero-card-meta">{card.author} · {card.year ?? "n.d."}</p><p className="hero-card-title">{card.title}</p>
        {card.chip === "RETRACTED" && <span className="hero-card-stamp" aria-hidden>Retracted</span>}
      </motion.article>
    </motion.div>
  </li>;
}

// A numbered reference slot on the paper: empty rule until its card lands, then the reference with its finding.
function PaperSlot({ index, filled, reduced, delay }: { index: number; filled: boolean; reduced: boolean; delay: number }) {
  const card = heroCards[index], style = findingStyles[card.chip], quick = reduced ? { duration: 0 } : null;
  return <li className="paper-slot hero-slot" data-slot={index + 1} data-filled={filled} data-chip={card.chip}>
    <span className="paper-slot-number">[{index + 1}]</span>
    <span className="paper-slot-body">
      <motion.span aria-hidden className="paper-slot-empty" initial={false} animate={{ opacity: filled ? 0 : 1 }} transition={quick ?? { duration: .12, delay }} />
      <motion.span className="paper-slot-fill" initial={false} animate={filled ? { opacity: 1, y: reduced ? 0 : [0, 3, 0] } : { opacity: 0, y: 0 }} transition={quick ?? { opacity: { duration: .14, delay }, y: { duration: .12, delay, ease: "easeOut" } }}>
        <motion.span aria-hidden className="paper-slot-bar" style={{ background: style.color }} initial={false} animate={{ scaleY: filled ? 1 : 0 }} transition={quick ?? { duration: .16, delay }} />
        <span className="paper-slot-ref"><strong>{card.author} {card.year ?? "n.d."}.</strong> <em>{card.title}</em></span>
        <motion.span className="paper-slot-verdict" initial={false} animate={{ opacity: filled ? 1 : 0 }} transition={quick ?? { duration: .16, delay: delay + .15 }}><Finding chip={card.chip} /></motion.span>
      </motion.span>
    </span>
  </li>;
}

export function LandingScene() {
  const scene = useRef<HTMLElement>(null), stage = useRef<HTMLDivElement>(null), paperSlot = useRef<HTMLDivElement>(null), paper = useRef<HTMLDivElement>(null), list = useRef<HTMLOListElement>(null);
  const reduced = useSceneReducedMotion(), pinned = !useMediaQuery("(max-width: 899px)");
  const { scrollYProgress } = useScroll({ target: scene, offset: ["start start", "end end"] });
  const progress = useTransform(scrollYProgress, p => reduced ? 1 : p);
  const [targets, setTargets] = useState<Target[]>([]);
  // `fit` shrinks the paper (transform only) so the whole page, tally included, fits the stage at any desktop height.
  const [fit, setFit] = useState(1);
  const paperY = useTransform(progress, [0, RISE_END], ["34%", "0%"]), paperScale = useTransform(progress, p => fit * (.94 + .06 * clamp01(p / RISE_END)));
  const [landed, setLanded] = useState(0);
  const listSeen = useInView(list, { once: true, amount: .4 });
  useMotionValueEvent(progress, "change", p => setLanded(landedBy(p)));
  useEffect(() => {
    // ResizeObserver reports once on observe, so this also takes the first measurement.
    const measure = () => {
      setLanded(landedBy(progress.get()));
      if (!stage.current || !paperSlot.current || !paper.current) return;
      // Slots are measured with offsets (transform-free) against the untransformed paper slot.
      const origin = paperSlot.current.getBoundingClientRect();
      const cards = [...stage.current.querySelectorAll<HTMLElement>(".hero-card-slot")];
      if (!cards.length) { setFit(1); return; } // Mobile shows no flying cards and does not scale the paper.
      const page = paper.current, f = Math.min(1, paperSlot.current.clientHeight / page.offsetHeight), mid = page.offsetLeft + page.offsetWidth / 2;
      setFit(f);
      setTargets([...paper.current.querySelectorAll<HTMLElement>(".paper-slot")].map((slot, i) => {
        let x = slot.offsetLeft, y = slot.offsetTop;
        for (let n = slot.offsetParent as HTMLElement | null; n && n !== paper.current && paper.current!.contains(n); n = n.offsetParent as HTMLElement | null) { x += n.offsetLeft; y += n.offsetTop; }
        const r = cards[i].getBoundingClientRect();
        // The paper scales by `f` from its top centre.
        return { dx: origin.left + mid + (x + slot.offsetWidth / 2 - page.offsetWidth / 2) * f - (r.left + r.width / 2), dy: origin.top + page.offsetTop + (y + slot.offsetHeight / 2) * f - (r.top + r.height / 2), scale: Math.min(1.4, slot.offsetWidth * f / cards[i].offsetWidth) };
      }));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(stage.current!);
    return () => observer.disconnect();
  }, [progress]);
  const isFilled = (index: number) => pinned ? order.indexOf(index) < landed : reduced || listSeen;
  const tallyShown = pinned ? landed === order.length : reduced || listSeen;
  return <section ref={scene} id="overview" className="hero-scene" aria-labelledby="headline">
    <div ref={stage} className="hero-stage">
      <div className="hero-copy">
        <h1 id="headline" data-reveal>Read your paper like<br className="desktop-break" /> Reviewer 2 would.</h1>
        <p className="hero-lead">VerRes checks every reference in your manuscript, finds the passage you cited, and flags where a claim goes further than its source — before anyone else does.</p>
        <div className="hero-actions"><a className="pill-button" href="#submit">Review a paper</a><Link className="outline-button" href="/report/sample-paper3">See a sample report</Link></div>
        <p className="hero-caption">Every finding links to its evidence.</p>
      </div>
      {pinned && <ul className="hero-cards" aria-hidden>{heroCards.map((card, i) => <HeroCard key={card.id} index={i} progress={progress} target={targets[i]} reduced={reduced} />)}</ul>}
      <div ref={paperSlot} className="hero-paper-slot">
        <motion.div ref={paper} className="hero-paper" style={pinned ? { y: paperY, scale: paperScale, "--fit": fit } as MotionStyle : undefined}>
          <p className="paper-title">{heroPaper.title}</p>
          <p className="paper-byline">{heroPaper.byline}</p>
          <p className="paper-abstract"><span>Abstract.</span> {heroPaper.abstract.join(" ")}</p>
          <p className="paper-references-heading">References</p>
          <ol ref={list} className="paper-references" aria-label="References with their findings">{heroCards.map((card, i) => <PaperSlot key={card.id} index={i} filled={isFilled(i)} reduced={reduced} delay={pinned ? 0 : i * .12} />)}</ol>
          <motion.ul className="hero-tally" aria-label="Findings across the eight references" initial={false} animate={{ opacity: tallyShown ? 1 : 0, y: tallyShown || reduced ? 0 : 6 }} transition={{ duration: reduced ? 0 : .24, delay: pinned || reduced ? 0 : heroCards.length * .12 }}>
        {heroTally.map(({ chip, count }) => <li key={chip} style={{ color: findingStyles[chip].text, borderColor: findingStyles[chip].color }}>{count} {findingStyles[chip].short}</li>)}
      </motion.ul>
        </motion.div>
      </div>
      <p className="hero-scroll-caption" aria-hidden>Scroll. {countWord(heroCards.length)} references, one reviewed page.</p>
    </div>
  </section>;
}
