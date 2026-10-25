"use client";
import { usePolishMotion } from "./landing-chrome";
import { useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, Square, CircleAlert } from "lucide-react";
import NumberFlow from "@number-flow/react";
import type { Report } from "@/lib/report";
import { fixTarget, hasReviewReceipt, reviewComments, reviewState } from "@/lib/review";
import { motionTokens } from "@/lib/motion";
import { VerdictBadge } from "./verdict-badge";
import { ReportSkeleton } from "./report-chrome";

const reviewers = [["METHODS", "R1 Methods"], ["EVIDENCE", "R2 Evidence"], ["CLAIMS", "R3 Claims"]] as const;
const timing = { duration: motionTokens.fade.duration * 1000, easing: "ease-out" };
export function PeerReview({ report, onLocate }: { report: Report | null; onLocate: (target: string) => void }) {
  const reduced = usePolishMotion();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  if (!report) return <ReportSkeleton label="Loading peer review" />;
  const state = reviewState(report), comments = reviewComments(report);
  return <div className="space-y-5">
    {state.hidden && <div role="alert" className="flex items-start gap-3 rounded-xl border border-destructive/25 bg-white p-5 text-sm leading-6 text-destructive"><AlertTriangle size={18} className="mt-1 shrink-0" /><p>This PDF contains hidden instructions aimed at AI reviewers. The panel ignored them.</p></div>}
    <section aria-label="Area chair" className="report-card border bg-white p-6 md:p-8">
      <p className="mb-2 text-[10px] tracking-[.12em] text-muted-foreground uppercase">The panel’s priorities</p><h2 className="font-serif text-3xl">Area chair</h2>
      {state.failed ? <div role="status" className="mt-5 space-y-3"><h3 className="text-sm font-medium">Review incomplete</h3><VerdictBadge /><p className="text-sm leading-6 text-muted-foreground">{report.review?.warning || "The panel could not finish. Citation and claim evidence remain available."}</p></div> : <>
        {state.running && <p role="status" className="mt-4 text-sm text-muted-foreground">Panel still running. Reviewer evidence appear as they arrive.</p>}
        <h3 className="mt-5 text-sm font-medium">Top 5 fixes</h3>
        <ol className="mt-4 divide-y text-sm leading-6">{report.review?.top_fixes?.slice(0, 5).map((fix, i) => {
          const target = fixTarget(report, fix);
          return <li key={i} className="flex items-start gap-3 py-4 break-words"><Square size={16} className="mt-1 shrink-0 text-muted-foreground" aria-hidden /><span>{target ? <a href={`#${encodeURIComponent(target)}`} onClick={e => { e.preventDefault(); onLocate(target); }} className="underline decoration-border underline-offset-4 hover:decoration-foreground">{fix}</a> : <>{fix}<span className="ml-2 text-xs text-muted-foreground">Linked evidence unavailable. Needs review.</span></>}</span></li>;
        })}</ol>
        {!report.review?.top_fixes?.length && <p className="mt-3 text-sm text-muted-foreground">{state.running ? "Waiting for the area chair’s fixes." : "No prioritized fixes were returned. Inspect the reviewer evidence."}</p>}
      </>}
    </section>
    <div className="grid items-start gap-4 lg:grid-cols-3">{reviewers.map(([reviewer, name], i) => {
      const concerns = comments.filter(c => c.reviewer === reviewer);
      const major = concerns.filter(c => c.severity === "MAJOR").length, minor = concerns.filter(c => c.severity === "MINOR").length;
      return <motion.section layout={!reduced} key={reviewer} aria-label={name} className="report-card min-w-0 border bg-white p-6" initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ ...motionTokens.fade, delay: reduced ? 0 : i * motionTokens.reviewStagger }}>
        <div className="flex items-center gap-3"><span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-full border bg-background text-xs font-medium">{name.split(" ").map(part => part[0]).join("")}</span><div><p className="mb-0.5 text-[9px] tracking-widest text-muted-foreground uppercase">Independent reviewer</p><h2 className="font-serif text-xl">{name}</h2></div></div>
        <p role="group" aria-label={`${major} major · ${minor} minor`} className="mt-3 text-xs text-muted-foreground"><span aria-hidden>{[major, minor].map((value, index) => <span key={index}><NumberFlow value={value} animated={!reduced} transformTiming={timing} spinTiming={timing} opacityTiming={timing} />{index === 0 ? " major · " : " minor"}</span>)}</span></p>
        <h3 className="mt-5 text-xs font-medium">Main concerns</h3>
        <ul className="mt-3 space-y-4 text-sm leading-6">{concerns.map((c, index) => <li key={index} className="break-words"><span className="mb-2 inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-[9px] font-medium uppercase"><CircleAlert size={10} aria-hidden />{c.severity.toLowerCase()}</span><p>{c.issue}</p><p className="mt-1 text-muted-foreground">{c.suggestion}</p></li>)}</ul>
        {!concerns.length && <p className="mt-3 text-sm text-muted-foreground">{state.running ? "Waiting for this reviewer." : "No concerns returned; this does not establish support. Needs review."}</p>}
        <details open={!!expanded[reviewer]} className="review-receipts mt-5 border-t pt-4 text-sm"><summary onClick={event => { event.preventDefault(); setExpanded(current => ({ ...current, [reviewer]: !current[reviewer] })); }} className="cursor-pointer">Evidence ({concerns.length})</summary><div className="mt-4 space-y-5">{concerns.map((c, index) => <div key={index} className="space-y-2 break-words">{hasReviewReceipt(report, c) ? <blockquote className="border-l-2 pl-3 font-serif leading-6">“{c.quote}”</blockquote> : <p><VerdictBadge /> Quote could not be verified in the paper.</p>}<p className="text-xs text-muted-foreground">Sentences: {c.sentence_ids.join(", ") || "Unavailable"}</p><p className="text-xs text-muted-foreground">Citations: {c.linked_citation_ids?.join(", ") || "None linked"}</p></div>)}</div></details>
      </motion.section>;
    })}</div>
  </div>;
}
