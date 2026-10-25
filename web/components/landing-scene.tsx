"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, useInView, useMotionValueEvent, useScroll, useTransform, type MotionValue } from "motion/react";
import { countWord, heroCards, heroChipLabels } from "@/lib/landing-data";
import { useMediaQuery, useSceneReducedMotion } from "./landing-chrome";
import { MockupImage } from "./mockup-image";

// Resting slots around the headline: [side, inset %, top %, rotation°]. Landing order interleaves left and right.
const slots = [["left", 2.5, 9, -4], ["right", 3, 7, 3.5], ["left", 9, 33, 2.5], ["right", 9.5, 31, -3], ["left", 1.5, 56, -2], ["right", 2, 54, 4], ["left", 10, 76, 3], ["right", 11, 77, -2.5]] as const;
const order = [3, 0, 6, 1, 5, 2, 7, 4];
const FLIGHT = { start: .15, stagger: .06, length: .28 };
const RISE_END = .4;
// The laptop screen inside S1, as fractions of the frame (centre point).
const SCREEN = { x: .595, y: .425 };
const landAt = (rank: number) => FLIGHT.start + rank * FLIGHT.stagger + FLIGHT.length;
const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
const easeInOut = (t: number) => t < .5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

type Target = { dx: number; dy: number };
function HeroCard({ index, progress, target, pinned, reduced }: { index: number; progress: MotionValue<number>; target?: Target; pinned: boolean; reduced: boolean }) {
  const card = heroCards[index], [side, inset, top, rotation] = slots[index], rank = order.indexOf(index), start = FLIGHT.start + rank * FLIGHT.stagger;
  const flight = (p: number) => easeInOut(clamp01((p - start) / FLIGHT.length));
  const transform = useTransform(progress, p => {
    const e = flight(p), dx = target?.dx ?? 0, dy = target?.dy ?? 0, cx = dx / 2 - dy * .25, cy = dy / 2 + dx * .25;
    return `translate3d(${2 * (1 - e) * e * cx + e * e * dx}px,${2 * (1 - e) * e * cy + e * e * dy}px,0) rotate(${rotation * (1 - e)}deg) scale(${1 - .68 * e})`;
  });
  const opacity = useTransform(progress, p => { const t = clamp01((p - start) / FLIGHT.length); return t < .7 ? 1 : 1 - (t - .7) / .3; });
  const bob = pinned && !reduced;
  return <li className="hero-card-slot" style={{ [side]: `${inset}%`, top: `${top}%` }}>
    <motion.div className="hero-card-flight" style={pinned ? { transform, opacity } : undefined}>
      <motion.article className="hero-card" initial={false} animate={bob ? { y: [0, 6, -6, 0], rotate: [0, .7, -.7, 0] } : { y: 0, rotate: 0 }} transition={bob ? { duration: 6 + (index % 4), repeat: Infinity, ease: "easeInOut", delay: index * .35 } : { duration: 0 }}>
        <p className="hero-card-meta">{card.author} · {card.year ?? "n.d."}</p><p className="hero-card-title">{card.title}</p>
      </motion.article>
    </motion.div>
  </li>;
}

function HeroChipItem({ index, landed, reduced }: { index: number; landed: boolean; reduced: boolean }) {
  const card = heroCards[index], [glyph, label, tone] = heroChipLabels[card.chip];
  return <motion.li className={`hero-chip ${tone}`} initial={false} animate={landed ? { opacity: 1, scale: reduced ? 1 : [.9, 1.06, 1] } : { opacity: 0, scale: .9 }} transition={{ duration: reduced ? 0 : landed ? .16 : .12, ease: [.2, .7, .2, 1] }}>
    <span aria-hidden>{glyph}</span> {label}<span className="sr-only">: {card.author}, {card.year ?? "n.d."}</span>
  </motion.li>;
}

export function LandingScene() {
  const scene = useRef<HTMLElement>(null), stage = useRef<HTMLDivElement>(null), slot = useRef<HTMLDivElement>(null), chips = useRef<HTMLUListElement>(null);
  const reduced = useSceneReducedMotion(), pinned = !useMediaQuery("(max-width: 899px)");
  const { scrollYProgress } = useScroll({ target: scene, offset: ["start start", "end end"] });
  const progress = useTransform(scrollYProgress, p => reduced ? 1 : p);
  const laptopY = useTransform(progress, [0, RISE_END], ["30%", "0%"]), laptopScale = useTransform(progress, [0, RISE_END], [.9, 1]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [landed, setLanded] = useState(0);
  const chipsSeen = useInView(chips, { once: true, amount: .6 });
  useMotionValueEvent(progress, "change", p => setLanded(order.filter((_, rank) => p >= landAt(rank)).length));
  useEffect(() => {
    // ResizeObserver reports once on observe, so this also takes the first measurement.
    const measure = () => {
      setLanded(order.filter((_, rank) => progress.get() >= landAt(rank)).length);
      if (!stage.current || !slot.current) return;
      const area = slot.current.getBoundingClientRect();
      const height = Math.min(area.height, area.width / 1.5), width = height * 1.5;
      const tx = area.left + (area.width - width) / 2 + SCREEN.x * width, ty = area.top + (area.height - height) / 2 + SCREEN.y * height;
      setTargets([...stage.current.querySelectorAll<HTMLElement>(".hero-card-slot")].map(card => { const r = card.getBoundingClientRect(); return { dx: tx - (r.left + r.width / 2), dy: ty - (r.top + r.height / 2) }; }));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(stage.current!);
    return () => observer.disconnect();
  }, [progress]);
  const isLanded = (index: number) => pinned ? order.indexOf(index) < landed : reduced || chipsSeen;
  return <section ref={scene} className="hero-scene" aria-labelledby="headline">
    <div ref={stage} className="hero-stage">
      <div className="hero-copy">
        <h1 id="headline" data-reveal>Read your paper like<br className="desktop-break" /> Reviewer 2 would.</h1>
        <p className="hero-lead">VerRes checks every reference in your manuscript, finds the passage you cited, and flags where a claim goes further than its source — before anyone else does.</p>
        <div className="hero-actions"><a className="pill-button" href="#submit">Review a paper</a><Link className="outline-button" href="/report/sample-paper3">See a sample report</Link></div>
        <p className="hero-caption">Every finding links to its evidence.</p>
      </div>
      <ul className="hero-cards" aria-label="References from two recorded manuscripts">{heroCards.map((card, i) => <HeroCard key={card.id} index={i} progress={progress} target={targets[i]} pinned={pinned} reduced={reduced} />)}</ul>
      <div ref={slot} className="hero-laptop-slot"><motion.div className="hero-laptop" style={pinned ? { y: laptopY, scale: laptopScale } : undefined}><MockupImage scene="s1" priority sizes="(max-width: 899px) 100vw, 60vw" alt="A recorded VerRes paper review on a library laptop" /></motion.div></div>
      <ul ref={chips} className="hero-chips" aria-label="Verdicts, one per reference">{order.map(i => <HeroChipItem key={heroCards[i].id} index={i} landed={isLanded(i)} reduced={reduced} />)}</ul>
      <p className="hero-scroll-caption" aria-hidden>Scroll. {countWord(heroCards.length)} references become one report.</p>
    </div>
  </section>;
}
