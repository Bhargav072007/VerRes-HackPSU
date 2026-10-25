"use client";
import { memo, useEffect, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { ArrowLeft, ArrowRight, Check, Minus } from "lucide-react";
import { useJobStream } from "@/hooks/useJobStream";
import { jobCounts, stageStatus, type Row } from "@/lib/job-stream";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { VerdictBadge } from "@/components/verdict-badge";
import { counterTiming, motionTokens } from "@/lib/motion";
import { LandingChrome, receiptNavigate, usePolishMotion } from "./landing-chrome";
import { toast } from "sonner";

const phases = [
  { key: "parse", label: "Parse", description: "Read the paper and extract its references." },
  { key: "existence", label: "Resolve", description: "Look up references in Crossref, OpenAlex and arXiv." },
  { key: "retraction", label: "Retractions", description: "Check the record for retraction notices." },
  { key: "source", label: "Sources", description: "Retrieve the passages behind the references." },
  { key: "support", label: "Verify", description: "Compare claims with source passages and verify quotes." },
  { key: "review", label: "Peer review", description: "Gather three perspectives and the area chair summary." },
];
const ReferenceRow = memo(function ReferenceRow({ row, index }: { row: Row; index: number }) {
  const e = row.existence, r = row.retraction;
  const verified = e?.status === "VERIFIED" && r?.status === "NONE";
  const label = r?.status === "RETRACTED" ? "Retracted" : r && r.status !== "NONE" ? "Needs review" : e?.status === "NOT_FOUND" ? "Not found" : verified ? "Verified" : e ? "Needs review" : "Pending";
  return <li data-reference-id={row.reference.id} className="reference-row" style={{ "--i": Math.min(index, 3) } as CSSProperties}>
    <div className="flex flex-wrap items-start gap-3 sm:flex-nowrap">
      <span className="mt-1 text-[10px] text-muted-foreground tabular-nums">{String(index + 1).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1 basis-48 sm:basis-auto"><p className="text-sm leading-6">{row.reference.title || row.reference.raw_text}</p>
        <span className="mt-1 inline-block rounded-full border px-2 py-0.5 text-[9px] text-muted-foreground">{row.cachedAt ? `from cache ${new Date(row.cachedAt).toLocaleTimeString()}` : "live"}</span>
      </div>
      <span data-chip={label} className="ml-7 inline-flex min-w-24 items-center sm:mt-1 sm:ml-0">
        <span key={label} className="verdict-flip">
          {label === "Pending" ? <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Minus size={12} />Pending</span> : <VerdictBadge status={r?.status === "RETRACTED" ? "RETRACTED" : e?.status === "NOT_FOUND" ? "NOT_FOUND" : verified ? "VERIFIED" : "NEEDS_REVIEW"} />}
        </span>
      </span>
    </div>
    {(e || r) && <details className="mt-2 pl-7 text-xs leading-5 text-muted-foreground"><summary className="cursor-pointer">Receipts & reason</summary>{e && <p className="mt-2">{e.status === "NOT_FOUND" ? "Not found in Crossref, OpenAlex or arXiv. " : ""}{e.reason}</p>}{r && <p>{r.reason}</p>}{[...(e?.receipt_urls ?? []), ...(r?.notice_urls ?? [])].filter(url => typeof url === "string" && /^https?:\/\//.test(url)).map(url => <a key={url} className="block break-all underline" href={url} target="_blank" rel="noreferrer">{url}</a>)}</details>}
  </li>;
});

export function LiveCheck({ id, report = false }: { id: string; report?: boolean }) {
  const state = useJobStream(id), router = useRouter(), reduced = usePolishMotion();
  const [leaving, setLeaving] = useState(false);
  const counts = jobCounts(state);
  const rows = Object.values(state.rows).filter(row => row.reference);
  const statuses = phases.map(({ key }) => {
    if (key !== "source" && key !== "support") return stageStatus(state, key);
    const tasks = Object.entries(state.stages).filter(([name]) => name.startsWith(`${key}:`)).map(([, status]) => status);
    if (!tasks.length) return state.stages[key];
    if (tasks.includes("CHECK_INCOMPLETE")) return "CHECK_INCOMPLETE";
    const expected = key === "source" ? rows.length : state.paper?.citations?.length || 0;
    return tasks.includes("STARTED") || tasks.length < expected ? "STARTED" : "COMPLETED";
  });
  const pendingIndex = statuses.findIndex(status => status === "STARTED" || status == null);
  const activeIndex = pendingIndex < 0 ? 5 : pendingIndex;
  const active = phases[state.done ? 5 : activeIndex];
  const happening = state.done ? "Your findings and receipts are ready to read." : Object.keys(state.errors).length ? "Some checks need review. Available receipts will remain visible below." : active.description;
  const href = `/report/${encodeURIComponent(id)}`;
  useEffect(() => {
    if (!state.done || report) return;
    toast.success("Your review is ready. Findings and receipts included.", { id: `review-${id}` });
    const fade = setTimeout(() => setLeaving(true), reduced ? 1500 : 1280);
    const timer = setTimeout(() => receiptNavigate(router.push, href), 1500);
    return () => { clearTimeout(fade); clearTimeout(timer); };
  }, [state.done, report, href, router, reduced, id]);
  return <main id="main" className="live-check polished-page" data-leaving={leaving}>
    <LandingChrome live />
    <div className="section-container live-content">
      <Link href="/" className="live-back"><ArrowLeft size={14} /> Back to VerRes</Link>
      <motion.header layoutId="job" transition={reduced ? { duration: 0 } : motionTokens.layout} className="live-header" aria-label="Paper under review"><div><p className="section-pill">● 02 · The review</p><h1>{state.done ? "Your review is ready." : "Following the evidence."}</h1><p>{state.paper?.title || "Reading your paper and gathering its references."}</p></div>{state.done && !report && <Button asChild><Link href={href}>View report <ArrowRight size={14} /></Link></Button>}</motion.header>
      <div aria-label="Review counters" className="live-counters">
        <span role="status" aria-label={`${counts.checked} / ${counts.total} citations checked`}><strong><NumberFlow aria-hidden value={counts.checked} animated={!reduced} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={counterTiming} /><span className="counter-slash"> / </span><NumberFlow aria-hidden value={counts.total} animated={!reduced} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={counterTiming} /></strong><span>citations checked</span></span>
        {([[counts.missing, "not found", "NOT_FOUND"], [counts.retracted, "retracted", "RETRACTED"], [counts.partiallySupported, "Partially supported", "PARTIALLY_SUPPORTED"], [counts.needsReview, "need review", "NEEDS_REVIEW"]] as const).map(([value, label, verdict]) => <span key={label} aria-label={`${value} ${label}`}><strong><NumberFlow aria-hidden value={value} animated={!reduced} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={counterTiming} /></strong><VerdictBadge status={verdict} /></span>)}
      </div>
      <div className="live-grid"><nav className="stage-rail" aria-label="Review stages"><ol>{phases.map(({ key, label, description }, i) => {
        const status = statuses[i], done = status === "COMPLETED", current = !state.done && i === activeIndex;
        return <li key={key} data-complete={done} aria-current={current ? "step" : undefined}><span className="stage-stop">{done ? <Check size={12} /> : i + 1}</span><div><span className="stage-name">{label}</span>{current && <span className="current-stage">CURRENT STAGE</span>}{current && <p>{description}</p>}{status === "CHECK_INCOMPLETE" && <span className="stage-incomplete">? Needs review</span>}</div></li>;
      })}</ol><div className="stage-segments" aria-hidden="true">{statuses.map((status, i) => <span key={i} data-complete={status === "COMPLETED"} />)}</div><div className="stage-progress"><span>Stage {state.done ? 6 : activeIndex + 1} of 6</span><span>Paper to receipts</span></div><p className="stage-parallel">Some checks run in parallel.<br />Each stage keeps its own record.</p></nav>
      <div className="live-panels"><p aria-live="polite" className="happening"><span>{state.done ? "Ready" : "Happening now"}</span>{happening}</p>
        <section className="stage-panel crosshair" aria-label="Current stage checks"><p className="eyebrow">{String((state.done ? 5 : activeIndex) + 1).padStart(2, "0")} / {active.label.toUpperCase()}</p><h2>{state.done ? "Checks recorded. Receipts ready." : active.description}</h2><ol>{(active.key === "parse" ? [{ id: "paper", title: state.paper?.title || "Reading paper text and references", status: statuses[0] }]
          : active.key === "review" ? [{ id: "review", title: "Three reviewers and the area chair summary", status: statuses[5] }]
          : active.key === "support" ? (state.paper?.citations || []).map(citation => ({ id: citation.id, title: citation.claim_text, status: state.stages[`support:${citation.id}`] }))
          : rows.map(row => ({ id: row.reference.id, title: row.reference.title || row.reference.raw_text, status: state.stages[`${active.key}:${row.reference.id}`] || (active.key === "existence" && row.existence ? "COMPLETED" : active.key === "retraction" && row.retraction ? "COMPLETED" : undefined) }))).map((task, i) => {
          const row = state.rows[task.id];
          const uncertain = state.done && task.status !== "COMPLETED" || active.key === "support" && state.support[task.id]?.label === "NEEDS_REVIEW" || task.status === "CHECK_INCOMPLETE" || active.key === "existence" && row?.existence && !["VERIFIED", "NOT_FOUND"].includes(row.existence.status) || active.key === "retraction" && row?.retraction && !["NONE", "RETRACTED"].includes(row.retraction.status);
          const flagged = active.key === "support" && state.support[task.id] && !["SUPPORTED", "NEEDS_REVIEW"].includes(state.support[task.id].label) || active.key === "existence" && row?.existence?.status === "NOT_FOUND" || active.key === "retraction" && row?.retraction?.status === "RETRACTED";
          const hasResult = active.key === "existence" ? !!row?.existence : active.key === "retraction" ? !!row?.retraction : active.key === "support" ? !!state.support[task.id] : true;
          const done = task.status === "COMPLETED" && hasResult && !flagged && !uncertain;
          return <li className="stage-task" key={`${active.key}:${task.id}`} style={{ "--i": Math.min(i, 3) } as CSSProperties}><span>{task.title}</span><span key={`${task.status}:${flagged}:${uncertain}`} className={`status-pill ${uncertain ? "blue" : flagged ? "red" : done ? "sage" : "checking"}`}>{uncertain ? "? NEEDS REVIEW" : flagged ? "✕ FLAGGED" : done ? "✓ PASSED" : "◌ CHECKING"}</span></li>;
        })}</ol><p className="stage-note">Stage status describes the check. Source and claim verdicts remain separate.</p></section>
        <section aria-label="References" className="references-panel"><div className="references-heading"><h2>Reference by reference.</h2><span>Receipts, not scores.</span></div>
          {Object.entries(state.errors).map(([key, reason]) => <p role="alert" key={key} className="live-error">{reason}</p>)}
          {!state.paper ? <div aria-label="Loading references" className="space-y-6 p-5">{[0, 1, 2, 3].map(i => <div key={i} className="space-y-2"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-1/3" /></div>)}</div> : <ol>{rows.map((row, index) => <ReferenceRow key={row.reference.id} row={row} index={index} />)}</ol>}
          {state.paper && !state.paper.references?.length && <p className="live-empty">No references were extracted. Needs review.</p>}
        </section>
      </div></div>
    </div>
  </main>;
}
