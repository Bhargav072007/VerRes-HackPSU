"use client";
import { memo, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { ArrowLeft, ArrowRight, Check, Minus } from "lucide-react";
import { useJobStream } from "@/hooks/useJobStream";
import { jobCounts, stages, stageStatus, type Row } from "@/lib/job-stream";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { VerdictBadge } from "@/components/verdict-badge";
import { counterTiming, motionTokens } from "@/lib/motion";

const labels = ["Read paper", "Extract references", "Find sources", "Check retractions", "Verify claims", "Peer review", "Prepare report"];
const activity = ["Reading the paper text.", "Extracting citations and references.", "Looking up references in Crossref, OpenAlex and arXiv.", "Checking for retraction notices.", "Comparing claims with source passages and verifying quotes.", "Gathering reviewer comments and the area chair summary.", "Organizing findings and their receipts."];
const ReferenceRow = memo(function ReferenceRow({ row, index }: { row: Row; index: number }) {
  const reduced = useReducedMotion();
  const e = row.existence, r = row.retraction;
  const verified = e?.status === "VERIFIED" && r?.status === "NONE";
  const label = r?.status === "RETRACTED" ? "Retracted" : r && r.status !== "NONE" ? "Needs review" : e?.status === "NOT_FOUND" ? "Not found" : verified ? "Verified" : e ? "Needs review" : "Pending";
  return <motion.li data-reference-id={row.reference.id} initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={reduced ? { duration: 0 } : { ...motionTokens.fade, delay: Math.min(index, 6) * motionTokens.stagger }} className="border-b px-5 py-5 last:border-0">
    <div className="flex flex-wrap items-start gap-3 sm:flex-nowrap">
      <span className="mt-1 text-[10px] text-muted-foreground tabular-nums">{String(index + 1).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1 basis-48 sm:basis-auto"><p className="text-sm leading-6">{row.reference.title || row.reference.raw_text}</p>
        <span className="mt-1 inline-block rounded-full border px-2 py-0.5 text-[9px] text-muted-foreground">{row.cachedAt ? `from cache ${new Date(row.cachedAt).toLocaleTimeString()}` : "live"}</span>
      </div>
      <span data-chip={label} className="ml-7 inline-flex min-w-24 items-center sm:mt-1 sm:ml-0">
        <AnimatePresence mode="wait" initial={false}><motion.span key={label} initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reduced ? { duration: 0 } : motionTokens.fade}>
          {label === "Pending" ? <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Minus size={12} />Pending</span> : <VerdictBadge status={r?.status === "RETRACTED" ? "RETRACTED" : e?.status === "NOT_FOUND" ? "NOT_FOUND" : verified ? "VERIFIED" : "NEEDS_REVIEW"} />}
        </motion.span></AnimatePresence>
      </span>
    </div>
    {(e || r) && <details className="mt-2 pl-7 text-xs leading-5 text-muted-foreground"><summary className="cursor-pointer">Receipts & reason</summary>{e && <p className="mt-2">{e.status === "NOT_FOUND" ? "Not found in Crossref, OpenAlex or arXiv. " : ""}{e.reason}</p>}{r && <p>{r.reason}</p>}{[...(e?.receipt_urls ?? []), ...(r?.notice_urls ?? [])].filter(url => typeof url === "string" && /^https?:\/\//.test(url)).map(url => <a key={url} className="block break-all underline" href={url} target="_blank" rel="noreferrer">{url}</a>)}</details>}
  </motion.li>;
});

export function LiveCheck({ id, report = false }: { id: string; report?: boolean }) {
  const state = useJobStream(id), router = useRouter(), reduced = useReducedMotion();
  const counts = jobCounts(state);
  const activeIndex = stages.findIndex(stage => stageStatus(state, stage) === "STARTED");
  const happening = state.done ? "Your findings and receipts are ready to read." : Object.keys(state.errors).length ? "Some checks need review. Available receipts will remain visible below." : activity[activeIndex < 0 ? 0 : activeIndex];
  const href = `/report/${encodeURIComponent(id)}`;
  useEffect(() => {
    if (!state.done || report) return;
    const timer = setTimeout(() => router.push(href), 1500);
    return () => clearTimeout(timer);
  }, [state.done, report, href, router]);
  return <main id="main" className="mx-auto max-w-6xl px-6 py-10 md:px-10">
    <Link href="/" className="inline-flex items-center gap-2 text-xs text-muted-foreground"><ArrowLeft size={14} /> Back to VerRes</Link>
    <div className="mt-8 flex flex-wrap items-end justify-between gap-4"><div><p className="text-[10px] tracking-[.2em] text-muted-foreground uppercase">{report ? "Review receipts" : "A little scrutiny, in progress"}</p><h1 className="mt-3 font-serif text-3xl">{state.done ? "Your review is ready." : "Following the evidence."}</h1><p className="mt-3 max-w-xl text-sm text-muted-foreground">{state.paper?.title || "Reading your paper and gathering its references."}</p></div>{state.done && !report && <Button asChild><Link href={href}>View report <ArrowRight size={14} /></Link></Button>}</div>
    <div aria-label="Review counters" className="my-8 flex flex-wrap gap-x-6 gap-y-4 rounded-xl border bg-white px-5 py-5 text-xs">
      <span role="status" aria-label={`${counts.checked} / ${counts.total} citations checked`}><NumberFlow aria-hidden value={counts.checked} animated={!reduced} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={counterTiming} /> / <NumberFlow aria-hidden value={counts.total} animated={!reduced} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={counterTiming} /> citations checked</span>
      {([[counts.missing, "not found", "NOT_FOUND"], [counts.retracted, "retracted", "RETRACTED"], [counts.overstated, "overstated", "PARTIALLY_SUPPORTED"], [counts.needsReview, "need review", "NEEDS_REVIEW"]] as const).map(([value, label, verdict]) => <span key={label} aria-label={`${value} ${label}`} className="inline-flex items-center gap-2"><NumberFlow aria-hidden value={value} animated={!reduced} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={counterTiming} /> <VerdictBadge status={verdict} /></span>)}
    </div>
    <p aria-live="polite" className="mb-6 min-h-12 text-sm leading-6 text-muted-foreground"><span className="mr-2 font-medium text-foreground">{state.done ? "Ready" : "Happening now"}</span>{happening}</p>
    <div className="grid items-start gap-8 md:grid-cols-[160px_1fr]">
      <nav aria-label="Review stages"><ol className="grid grid-cols-2 gap-x-3 gap-y-5 md:grid-cols-1 md:gap-6">{stages.map((stage, i) => {
        const status = stageStatus(state, stage), done = status === "COMPLETED", active = !state.done && (status === "STARTED" || (!state.seq && i === 0));
        return <li key={stage} aria-current={active && !done ? "step" : undefined} className="relative flex items-center gap-3 text-xs"><span className="flex size-7 shrink-0 items-center justify-center rounded-full border bg-white text-[10px]"><AnimatePresence mode="wait" initial={false}><motion.span key={done ? "done" : "pending"} initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reduced ? { duration: 0 } : motionTokens.fade}>{done ? <Check size={12} /> : String(i + 1).padStart(2, "0")}</motion.span></AnimatePresence></span><span className={active || done ? "" : "text-muted-foreground"}>{labels[i]}{status === "CHECK_INCOMPLETE" && <span className="block text-[9px]">Needs review</span>}</span>{active && !done && <motion.span aria-hidden className="absolute -bottom-2 left-10 h-px w-16 origin-left bg-foreground" initial={reduced ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={reduced ? { duration: 0 } : motionTokens.fade} />}</li>;
      })}</ol></nav>
      <section aria-label="References" className="min-w-0 overflow-hidden rounded-xl border bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-4"><h2 className="font-serif text-xl">Reference by reference.</h2><span className="text-[10px] text-muted-foreground">Receipts, not scores.</span></div>
        {Object.entries(state.errors).map(([key, reason]) => <p role="alert" key={key} className="border-b bg-secondary/40 px-5 py-3 text-xs leading-5">{reason}</p>)}
        {!state.paper ? <div aria-label="Loading references" className="space-y-6 p-5">{[0, 1, 2, 3].map(i => <div key={i} className="space-y-2"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-1/3" /></div>)}</div> : <ol>{Object.values(state.rows).filter(row => row.reference).map((row, index) => <ReferenceRow key={row.reference.id} row={row} index={index} />)}</ol>}
        {state.paper && !state.paper.references?.length && <p className="p-5 text-sm text-muted-foreground">No references were extracted. Needs review.</p>}
      </section>
    </div>
  </main>;
}
