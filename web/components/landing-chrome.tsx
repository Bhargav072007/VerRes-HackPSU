"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, Menu } from "lucide-react";

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

export function LandingChrome({ live = false }: { live?: boolean }) {
  const progress = useRef<HTMLSpanElement>(null);
  const [section, setSection] = useState(live ? "02 · THE REVIEW" : "FRONT MATTER");
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const total = document.documentElement.scrollHeight - innerHeight;
      progress.current?.style.setProperty("transform", `scaleX(${total > 0 ? scrollY / total : 0})`);
      if (!live) {
        const sections = [...document.querySelectorAll<HTMLElement>("[data-section]")];
        setSection(sections.reverse().find(node => node.getBoundingClientRect().top < innerHeight * .4)?.dataset.section || "FRONT MATTER");
      }
    };
    const scroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.setAttribute("data-visible", "true"); observer.unobserve(entry.target); }
    }), { threshold: .12 });
    document.querySelectorAll("[data-enter]").forEach(node => observer.observe(node));
    addEventListener("scroll", scroll, { passive: true });
    addEventListener("resize", scroll);
    update();
    document.dispatchEvent(new Event("verres:route-ready"));
    return () => { cancelAnimationFrame(frame); observer.disconnect(); removeEventListener("scroll", scroll); removeEventListener("resize", scroll); };
  }, [live]);
  return <header className="polish-nav"><Link className="polish-brand" href="/" aria-label="VerRes home"><BookOpen size={23} strokeWidth={1.5} /><strong>VerRes</strong><span className="beta-tag">BETA</span></Link><span className="nav-section">{section}</span><nav aria-label="Main navigation"><Link href="/#submit" aria-current={section.startsWith("01") ? "location" : undefined}>Upload</Link><Link href="/#how-it-works" aria-current={section.startsWith("02") ? "location" : undefined}>The checks</Link><Link href="/#honesty" aria-current={section.startsWith("03") ? "location" : undefined}>Our principle</Link></nav><details className="polish-menu"><summary aria-label="Navigation menu"><Menu size={15} /> Menu</summary><nav aria-label="Mobile navigation" onClick={event => { if ((event.target as HTMLElement).closest("a")) event.currentTarget.closest("details")?.removeAttribute("open"); }}><Link href="/#submit">Upload a paper</Link><Link href="/#how-it-works">The checks</Link><Link href="/#honesty">Our principle</Link></nav></details><Link className="pill-button" href="/#submit">Start a review <ArrowRight size={13} /></Link><span ref={progress} className="nav-progress" /></header>;
}

export function receiptNavigate(push: (href: string) => void, href: string) {
  if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.a11yMotion === "reduce") { push(href); return; }
  document.startViewTransition(() => new Promise<void>(resolve => {
    const finish = () => { clearTimeout(timer); document.removeEventListener("verres:route-ready", finish); resolve(); };
    const timer = setTimeout(finish, 360);
    document.addEventListener("verres:route-ready", finish, { once: true });
    push(href);
  }));
}
