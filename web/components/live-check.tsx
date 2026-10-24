"use client";
import { memo, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { ArrowLeft, ArrowRight, Check, CircleAlert, Minus } from "lucide-react";
import { useJobStream } from "@/hooks/useJobStream";
import { jobCounts, stages, type Row } from "@/lib/job-stream";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

const labels = ["Parse", "References", "Exists?", "Retracted?", "Supported?", "Review", "Report"];
const ReferenceRow = memo(function ReferenceRow({ row, index }: { row: Row; index: number }) {
  const reduced = useReducedMotion();
  const e = row.existence, r = row.retraction;
  const red = r?.status === "RETRACTED" || e?.status === "NOT_FOUND";
  const verified = e?.status === "VERIFIED" && (!r || r.status === "NONE");
  const label = r?.status === "RETRACTED" ? "Retracted" : r && r.status !== "NONE" ? "Needs review" : e?.status === "NOT_FOUND" ? "Not found" : verified ? "Verified" : e ? "Needs review" : "Pending";
  const Icon = red || label === "Needs review" ? CircleAlert : verified ? Check : Minus;
  return <motion.li data-reference-id={row.reference.id} initial={reduced ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .22, delay: reduced ? 0 : Math.min(index * .018, .35) }} className="border-b px-5 py-5 last:border-0">
    <div className="flex items-start gap-3">
      <span className="mt-1 text-[10px] text-muted-foreground tabular-nums">{String(index + 1).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1"><p className="text-sm leading-6">{row.reference.title || row.reference.raw_text}</p>
        <span className="mt-1 inline-block rounded-full border px-2 py-0.5 text-[9px] text-muted-foreground">{row.cachedAt ? `from cache ${new Date(row.cachedAt).toLocaleTimeString()}` : "live"}</span>
      </div>
      <motion.span data-chip={label} animate={{ backgroundColor: red ? "#fef0ed" : verified ? "#edf3eb" : e ? "#fff5dc" : "#efefec", color: red ? "#a32d24" : verified ? "#3d6245" : "#686b63" }} transition={{ duration: reduced ? 0 : .3 }} className="relative mt-1 inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px]">
        {red && <motion.span aria-hidden initial={{ opacity: 0 }} animate={reduced ? {} : { opacity: [0, .6, 0], scale: [1, 1.1, 1] }} transition={{ duration: .9 }} className="pointer-events-none absolute inset-0 rounded-full shadow-[0_0_12px_#d88f85]" />}
        <AnimatePresence mode="wait" initial={false}><motion.span key={label} className="inline-flex items-center gap-1.5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : .12 }}><Icon size={12} />{label}</motion.span></AnimatePresence>
      </motion.span>
    </div>
    {(e || r) && <details className="mt-2 pl-7 text-xs leading-5 text-muted-foreground"><summary className="cursor-pointer">Receipts & reason</summary>{e && <p className="mt-2">{e.status === "NOT_FOUND" ? "Not found in Crossref, OpenAlex or arXiv. " : ""}{e.reason}</p>}{r && <p>{r.reason}</p>}{[...(e?.receipt_urls ?? []), ...(r?.notice_urls ?? [])].filter(url => typeof url === "string" && /^https?:\/\//.test(url)).map(url => <a key={url} className="block break-all underline" href={url} target="_blank" rel="noreferrer">{url}</a>)}</details>}
  </motion.li>;
});

export function LiveCheck({ id, report = false }: { id: string; report?: boolean }) {
  const state = useJobStream(id), router = useRouter(), reduced = useReducedMotion();
  const counts = jobCounts(state);
  const href = `/report/${encodeURIComponent(id)}`;
  useEffect(() => {
    if (!state.done || report) return;
    const timer = setTimeout(() => router.push(href), 1500);
    return () => clearTimeout(timer);
  }, [state.done, report, href, router]);
  return <main id="main" className="mx-auto max-w-6xl px-6 py-10 md:px-10">
    <Link href="/" className="inline-flex items-center gap-2 text-xs text-muted-foreground"><ArrowLeft size={14} /> Back to VerRes</Link>
    <div className="mt-8 flex flex-wrap items-end justify-between gap-4"><div><p className="text-[10px] tracking-[.2em] text-muted-foreground uppercase">{report ? "Review receipts" : "A little scrutiny, in progress"}</p><h1 className="mt-3 font-serif text-3xl">{state.done ? "Your review is ready." : "Following the evidence."}</h1><p className="mt-3 max-w-xl text-sm text-muted-foreground">{state.paper?.title || "Reading your paper and gathering its references."}</p></div>{state.done && !report && <Button asChild><Link href={href}>View report <ArrowRight size={14} /></Link></Button>}</div>
    <div aria-label="Review counters" className="my-8 flex flex-wrap gap-x-6 gap-y-3 border-y py-4 text-xs">
      <span role="status" aria-label={`${counts.checked} / ${counts.total} citations checked`}><NumberFlow aria-hidden value={counts.checked} animated={!reduced} /> / <NumberFlow aria-hidden value={counts.total} animated={!reduced} /> citations checked</span>
      {([[counts.missing, "not found"], [counts.retracted, "retracted"], [counts.overstated, "overstated"], [counts.needsReview, "need review"]] as const).map(([value, label]) => <span key={label} aria-label={`${value} ${label}`} className="text-muted-foreground"><NumberFlow aria-hidden value={value} animated={!reduced} /> {label}</span>)}
    </div>
    <div className="grid items-start gap-8 md:grid-cols-[160px_1fr]">
      <nav aria-label="Review stages"><ol className="grid grid-cols-2 gap-4 md:grid-cols-1 md:gap-6">{stages.map((stage, i) => {
        const status = state.stages[stage], done = status === "COMPLETED", active = !state.done && (status === "STARTED" || (!state.seq && i === 0));
        return <li key={stage} aria-current={active && !done ? "step" : undefined} className="relative flex items-center gap-3 text-xs"><span className="flex size-6 items-center justify-center rounded-full border bg-white text-[10px]"><AnimatePresence mode="wait" initial={false}><motion.span key={done ? "done" : "pending"} initial={{ opacity: 0, rotateX: -90 }} animate={{ opacity: 1, rotateX: 0 }} exit={{ opacity: 0, rotateX: 90 }} transition={{ duration: reduced ? 0 : .18 }}>{done ? <Check size={12} /> : String(i + 1).padStart(2, "0")}</motion.span></AnimatePresence></span><span className={active || done ? "" : "text-muted-foreground"}>{labels[i]}{status === "CHECK_INCOMPLETE" && <span className="block text-[9px]">Needs review</span>}</span>{active && !done && <svg aria-hidden className="absolute -bottom-2 left-9 h-1 w-20" viewBox="0 0 80 2"><motion.path d="M0 1H80" stroke="#687d62" strokeWidth="2" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: reduced ? 0 : 1.4 }} /></svg>}</li>;
      })}</ol></nav>
      <section aria-label="References" className="min-w-0 overflow-hidden rounded-xl border bg-white">
        <div className="flex items-center justify-between border-b px-5 py-4"><h2 className="font-serif text-xl">Reference by reference.</h2><span className="text-[10px] text-muted-foreground">Receipts, not scores.</span></div>
        {Object.entries(state.errors).map(([key, reason]) => <p role="alert" key={key} className="border-b bg-amber-50 px-5 py-3 text-xs leading-5">{reason}</p>)}
        {!state.paper ? <div aria-label="Loading references" className="space-y-6 p-5">{[0, 1, 2, 3].map(i => <div key={i} className="space-y-2"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-1/3" /></div>)}</div> : <ol>{Object.values(state.rows).filter(row => row.reference).map((row, index) => <ReferenceRow key={row.reference.id} row={row} index={index} />)}</ol>}
        {state.paper && !state.paper.references?.length && <p className="p-5 text-sm text-muted-foreground">No references were extracted. Needs review.</p>}
      </section>
    </div>
  </main>;
}
