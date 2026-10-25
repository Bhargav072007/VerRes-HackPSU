"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useScroll } from "motion/react";
import Link from "next/link";
import { Brand } from "./brand";
const motionSnapshot = () => matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.a11yMotion === "reduce";
const motionServerSnapshot = () => true;
function subscribeMotion(update: () => void) {
  const media = matchMedia("(prefers-reduced-motion: reduce)");
  const observer = new MutationObserver(update);
  media.addEventListener("change", update);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-a11y-motion"] });
  return () => { media.removeEventListener("change", update); observer.disconnect(); };
}
export function usePolishMotion() {
  return useSyncExternalStore(subscribeMotion, motionSnapshot, motionServerSnapshot);
}
// Scroll scenes render their start state on the server; CSS shows the final state to reduced-motion readers before hydration.
export function useSceneReducedMotion() {
  return useSyncExternalStore(subscribeMotion, motionSnapshot, () => false);
}
export function useMediaQuery(query: string) {
  return useSyncExternalStore(update => { const media = matchMedia(query); media.addEventListener("change", update); return () => media.removeEventListener("change", update); }, () => matchMedia(query).matches, () => false);
}

export function LandingChrome({ live = false, report = false }: { live?: boolean; report?: boolean }) {
  return <header className="polish-nav" data-context={report ? "report" : live ? "live" : "landing"}><Link href="/" aria-label="VerRes home"><Brand /></Link><nav aria-label="Main navigation"><Link href="/#how-it-works">Method</Link><Link href="/#results">Results</Link><Link href="/#honesty">Limitations</Link></nav><details className="polish-menu"><summary aria-label="Navigation menu">Menu</summary><nav aria-label="Mobile navigation" onClick={e => { if ((e.target as HTMLElement).closest("a")) e.currentTarget.closest("details")?.removeAttribute("open"); }}><Link href="/#how-it-works">Method</Link><Link href="/#results">Results</Link><Link href="/#honesty">Limitations</Link></nav></details><Link className="pill-button" href="/#submit">Review a paper</Link></header>;
}
export function receiptNavigate(push: (href: string) => void, href: string) { push(href); }

// Landing only: a white bar that slides in after the hero, with the current section and page progress.
const sections = [["overview", "01 · Overview"], ["how-it-works", "02 · How it works"], ["results", "03 · Results"], ["anywhere", "04 · Anywhere"], ["honesty", "05 · Limitations"], ["submit", "06 · Review a paper"]] as const;
const links = [["how-it-works", "Method"], ["results", "Results"], ["honesty", "Limitations"]] as const;
export function StickyNav() {
  const reduced = usePolishMotion(), { scrollYProgress } = useScroll();
  const [shown, setShown] = useState(false), [active, setActive] = useState<string>("overview");
  useEffect(() => {
    const hero = document.getElementById("overview");
    const heroObserver = new IntersectionObserver(([entry]) => setShown(!entry.isIntersecting && entry.boundingClientRect.top < 0));
    const sectionObserver = new IntersectionObserver(entries => { for (const entry of entries) if (entry.isIntersecting) setActive(entry.target.id); }, { rootMargin: "-45% 0px -54% 0px" });
    if (hero) heroObserver.observe(hero);
    for (const [id] of sections) { const node = document.getElementById(id); if (node) sectionObserver.observe(node); }
    return () => { heroObserver.disconnect(); sectionObserver.disconnect(); };
  }, []);
  const label = sections.find(([id]) => id === active)?.[1] ?? sections[0][1];
  return <motion.div className="sticky-nav" data-shown={shown} inert={!shown} initial={false} animate={shown ? { y: 0, opacity: 1 } : { y: "-100%", opacity: 0 }} transition={{ duration: reduced ? 0 : .22, ease: [.2, 0, 0, 1] }}>
    <div className="sticky-nav-inner">
      <Link href="/" aria-label="VerRes home"><Brand /></Link>
      <span className="sticky-nav-label" aria-live="polite"><AnimatePresence mode="popLayout" initial={false}><motion.span key={label} initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={reduced ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, y: -6 }} transition={{ duration: .2, ease: [.2, .7, .2, 1] }}>{label}</motion.span></AnimatePresence></span>
      <nav aria-label="Section navigation">{links.map(([id, text]) => <Link key={id} href={`/#${id}`} aria-current={active === id ? "location" : undefined}>{text}</Link>)}</nav>
      <Link className="pill-button" href="/#submit">Review a paper</Link>
    </div>
    <motion.span aria-hidden className="sticky-nav-progress" style={{ scaleX: scrollYProgress }} />
  </motion.div>;
}
