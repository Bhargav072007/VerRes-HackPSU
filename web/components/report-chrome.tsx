"use client";
import { usePolishMotion } from "./landing-chrome";
import { useEffect, useState, forwardRef } from "react";
import { motion, useIsPresent } from "motion/react";
import { motionTokens } from "@/lib/motion";
import { BookOpen, CircleAlert } from "lucide-react";

export function ReportCompactHeader({ title, onVisibilityChange }: { title: string; onVisibilityChange: (visible: boolean) => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    let frame = 0;
    const update = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => {
      const summary = document.querySelector("[aria-label='Report summary']");
      const shown = !!summary && summary.getBoundingClientRect().bottom < 60;
      setVisible(shown); onVisibilityChange(shown);
    }); };
    update(); window.addEventListener("scroll", update, { passive: true }); window.addEventListener("resize", update);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", update); window.removeEventListener("resize", update); };
  }, [onVisibilityChange]);
  return <div className="compact-header" aria-hidden={!visible} inert={!visible} style={{ opacity: visible ? 1 : 0, transform: visible ? "none" : "translateY(-12px)", pointerEvents: visible ? "auto" : "none" }}><div className="flex min-h-16 items-center gap-3 px-4 sm:px-6"><BookOpen size={17} className="shrink-0" aria-hidden /><p className="min-w-0 flex-1 truncate font-serif text-sm" title={title}>{title}</p><div className="w-40 shrink-0" aria-hidden /></div></div>;
}

export function ReportState({ title, children, action, onAction }: { title: string; children: React.ReactNode; action?: string; onAction?: () => void }) {
  return <div className="report-card flex flex-col items-start border bg-white p-7 sm:p-10"><span className="mb-5 flex size-10 items-center justify-center rounded-md bg-secondary"><CircleAlert size={19} aria-hidden /></span><h2 className="font-serif text-2xl">{title}</h2><div className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">{children}</div>{action && <button onClick={onAction} className="mt-6 rounded-md bg-primary px-5 py-2.5 text-xs font-medium text-primary-foreground">{action}</button>}</div>;
}

export function ReportSkeleton({ label = "Loading your report…" }: { label?: string }) {
  return <div role="status" aria-label={label} className="report-card border bg-white p-7 sm:p-10"><span className="sr-only">{label}</span><div aria-hidden className="space-y-5"><div className="report-skeleton h-3 w-24" /><div className="report-skeleton h-7 w-3/4" />{[100, 92, 96, 72].map((width, i) => <div key={i} className="report-skeleton h-3" style={{ width: `${width}%` }} />)}</div></div>;
}

export const ReportTab = forwardRef<HTMLDivElement, { children: React.ReactNode }>(function ReportTab({ children }, ref) {
  const present = useIsPresent(), reduced = usePolishMotion();
  return <motion.div ref={ref} aria-hidden={!present} inert={!present} initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reduced ? { duration: 0 } : motionTokens.fade}>{children}</motion.div>;
});
