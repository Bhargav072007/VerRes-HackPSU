"use client";
import { memo, type CSSProperties } from "react";
import Link from "next/link";
import { ArrowLeft, Minus } from "lucide-react";
import { useJobStream } from "@/hooks/useJobStream";
import type { Row } from "@/lib/job-stream";
import { Skeleton } from "@/components/ui/skeleton";
import { VerdictBadge } from "@/components/verdict-badge";
import { LandingChrome } from "./landing-chrome";
import { ReviewRoom } from "./review-room";

const ReferenceRow = memo(function ReferenceRow({ row, index }: { row: Row; index: number }) {
  const e = row.existence, r = row.retraction;
  const verified = e?.status === "VERIFIED" && r?.status === "NONE";
  const label = r?.status === "RETRACTED" ? "Retracted" : r && r.status !== "NONE" ? "Needs review" : e?.status === "NOT_FOUND" ? "Not found" : verified ? "Verified" : e ? "Needs review" : "Pending";
  return <li data-reference-id={row.reference.id} className="reference-row" style={{ "--i": Math.min(index, 3) } as CSSProperties}>
    <div className="flex flex-wrap items-start gap-3 sm:flex-nowrap">
      <span className="mt-1 text-xs text-muted-foreground tabular-nums">{String(index + 1).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1 basis-48 sm:basis-auto"><p className="text-sm leading-6">{row.reference.title || row.reference.raw_text}</p>
        <span className="mt-1 inline-block rounded-md border px-2 py-0.5 text-xs text-muted-foreground">{row.cachedAt ? `from cache ${new Date(row.cachedAt).toLocaleTimeString()}` : "live"}</span>
      </div>
      <span data-chip={label} className="ml-7 inline-flex min-w-24 items-center sm:mt-1 sm:ml-0">
        <span key={label} className="verdict-flip">
          {label === "Pending" ? <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Minus size={12} />Pending</span> : <VerdictBadge status={r?.status === "RETRACTED" ? "RETRACTED" : e?.status === "NOT_FOUND" ? "NOT_FOUND" : verified ? "VERIFIED" : "NEEDS_REVIEW"} />}
        </span>
      </span>
    </div>
    {(e || r) && <details className="mt-2 pl-7 text-xs leading-5 text-muted-foreground"><summary className="cursor-pointer">Evidence & reason</summary>{e && <p className="mt-2">{e.status === "NOT_FOUND" ? "Not found in Crossref, OpenAlex or arXiv. " : ""}{e.reason}</p>}{r && <p>{r.reason}</p>}{[...(e?.receipt_urls ?? []), ...(r?.notice_urls ?? [])].filter(url => typeof url === "string" && /^https?:\/\//.test(url)).map(url => <a key={url} className="block break-all underline" href={url} target="_blank" rel="noreferrer">{url}</a>)}</details>}
  </li>;
});

export function LiveCheck({ id, report = false }: { id: string; report?: boolean }) {
  const state = useJobStream(id);
  const rows = Object.values(state.rows).filter(row => row.reference);
  return <main id="main" className="live-check polished-page">
    <LandingChrome live />
    <div className="section-container live-content">
      <Link href="/" className="live-back"><ArrowLeft size={14} /> Back to VerRes</Link>
      <ReviewRoom id={id} log={state.log} autoNavigate={!report} />
      <section aria-label="References" className="references-panel"><div className="references-heading"><h2>Reference by reference.</h2><span>Every finding links to its evidence.</span></div>
        {Object.entries(state.errors).map(([key, reason]) => <p role="alert" key={key} className="live-error">{reason}</p>)}
        {!state.paper ? <div aria-label="Loading references" className="space-y-6 p-5">{[0, 1, 2, 3].map(i => <div key={i} className="space-y-2"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-1/3" /></div>)}</div> : <ol>{rows.map((row, index) => <ReferenceRow key={row.reference.id} row={row} index={index} />)}</ol>}
        {state.paper && !state.paper.references?.length && <p className="live-empty">No references were extracted. Needs review.</p>}
      </section>
    </div>
  </main>;
}
