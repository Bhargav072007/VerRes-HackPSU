"use client";
import { useSyncExternalStore } from "react";
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
