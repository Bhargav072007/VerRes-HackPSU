"use client";
import { useRef } from "react";
import { Dialog } from "radix-ui";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowUpRight, FileSearch, Users, X } from "lucide-react";
import { VerdictBadge } from "@/components/verdict-badge";
import { evidenceDetails } from "@/lib/evidence";
import { motionTokens } from "@/lib/motion";
import type { Report } from "@/lib/report";

export function EvidencePanel({ report, citationId, onClose }: { report: Report; citationId: string; onClose: () => void }) {
  const reduced = useReducedMotion(), returnFocus = useRef<HTMLElement | null>(null);
  const citation = report.paper?.citations?.find(c => c.id === citationId);
  const data = citation && evidenceDetails(report, citation);
  return <Dialog.Root open={!!citation} onOpenChange={open => { if (!open) onClose(); }}>
    <AnimatePresence>
      {citation && data && <Dialog.Portal forceMount>
        <Dialog.Overlay asChild forceMount><motion.div className="fixed inset-0 z-50 bg-black/20" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={reduced ? { duration: 0 } : motionTokens.fade} /></Dialog.Overlay>
        <Dialog.Content asChild forceMount onOpenAutoFocus={() => { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; }} onCloseAutoFocus={event => {
          event.preventDefault();
          const target = returnFocus.current;
          if (target?.isConnected && target !== document.body) target.focus({ preventScroll: true });
          else document.querySelector<HTMLButtonElement>(`[data-citation-id="${CSS.escape(citationId)}"]`)?.focus({ preventScroll: true });
        }}>
          <motion.aside className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l bg-background shadow-xl sm:max-w-[620px] sm:rounded-l-xl" initial={reduced ? false : { x: 32, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: reduced ? 0 : 32, opacity: 0 }} transition={reduced ? { duration: 0 } : { x: { ...motionTokens.soft, restDelta: 1, restSpeed: 12 }, opacity: motionTokens.fade }}>
            <header className="flex shrink-0 items-center justify-between border-b bg-white px-6 py-5 sm:rounded-tl-xl sm:px-8">
              <div><Dialog.Title className="font-serif text-2xl">Evidence receipt</Dialog.Title><Dialog.Description className="mt-1 text-xs text-muted-foreground">Follow the claim to its source.</Dialog.Description></div>
              <Dialog.Close aria-label="Close evidence" className="rounded-md border p-2.5"><X size={18} /></Dialog.Close>
            </header>
            <div key={citation.id} className="min-h-0 overflow-y-auto overscroll-contain px-6 py-6 sm:px-8">
              <div className="flex flex-wrap items-center gap-2"><VerdictBadge status={data.verdict} />{data.mismatches.map((m, i) => <span key={i} className="rounded-md border bg-white px-2 py-1 text-[10px] text-muted-foreground">{m.replaceAll("_", " ").toLowerCase()}</span>)}</div>
              {data.needsReview && <p role="status" className="mt-4 rounded-xl border bg-white p-4 text-sm font-medium leading-6">{data.needsReview}</p>}
              <section className="mt-6 rounded-xl border bg-white p-5">
                <h3 className="mb-3 text-[10px] font-medium tracking-[.15em] text-muted-foreground uppercase">Your paper says</h3>
                {(report.paper?.sentences?.filter(s => citation.sentence_ids?.includes(s.id)) ?? []).map(s => {
                  const start = citation.claim_text ? s.text.indexOf(citation.claim_text) : -1;
                  return <p key={s.id} className="font-serif text-lg leading-8">{start < 0 ? s.text : <>{s.text.slice(0, start)}<mark className="bg-[#efede4] text-inherit">{citation.claim_text}</mark>{s.text.slice(start + citation.claim_text.length)}</>}</p>;
                })}
                {!report.paper?.sentences?.some(s => citation.sentence_ids?.includes(s.id)) && <p className="text-sm text-muted-foreground">Citing sentence unavailable. Needs review.</p>}
                {!!citation.claim_text && !report.paper?.sentences?.some(s => citation.sentence_ids?.includes(s.id) && s.text.includes(citation.claim_text)) && <p className="mt-3 font-serif text-lg"><mark className="bg-[#efede4] text-inherit">{citation.claim_text}</mark></p>}
              </section>
              <section className="mt-5 rounded-xl border bg-white p-5">
                <h3 className="mb-4 text-[10px] font-medium tracking-[.15em] text-muted-foreground uppercase">The source says</h3>
                {data.quotes.map((e, i) => <figure key={i} className="mt-4 first:mt-0">
                  <blockquote className="relative isolate font-serif text-lg leading-8"><motion.span aria-hidden data-quote-sweep className="pointer-events-none absolute inset-0 -z-10 origin-left rounded-sm bg-[#efede4]" initial={reduced ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: reduced ? 0 : .3, ease: "easeOut" }} />“{e.quote}”</blockquote>
                  <figcaption className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground"><span className="inline-flex items-center gap-1 rounded-md border px-2 py-1"><FileSearch size={12} />{data.source?.evidence_level === "FULL_TEXT" ? "Full text" : data.source?.evidence_level === "ABSTRACT_ONLY" ? "Abstract only" : "Metadata only"}</span><span>Verified verbatim · {e.passage_id}</span></figcaption>
                </figure>)}
                {!data.quotes.length && <p className="text-sm leading-6 text-muted-foreground">No verified source quote available. Needs review.</p>}
              </section>
              <p className="mt-5 text-sm leading-6">{data.verdict === "NOT_FOUND" ? "Not found in Crossref, OpenAlex or arXiv." : data.reason || "Claim support check incomplete. Needs review."}</p>
              {data.agreement && <p className="mt-4 inline-flex items-center gap-2 rounded-md border bg-white px-3 py-2 text-xs text-muted-foreground"><Users size={14} />{data.agreement}</p>}
              <nav aria-label="Evidence links" className="mt-6 space-y-2 border-t pt-5">{data.links.map(({ href, label }) => <a key={href} href={href} target="_blank" rel="noreferrer" className="flex items-start justify-between gap-3 rounded-lg border bg-white p-3 text-xs"><span className="min-w-0"><span className="font-medium">{label}</span><span className="mt-1 block break-all text-[10px] text-muted-foreground">{href}</span></span><ArrowUpRight size={14} className="shrink-0" /></a>)}{!data.links.length && <p className="text-xs text-muted-foreground">No receipt links available.</p>}</nav>
            </div>
          </motion.aside>
        </Dialog.Content>
      </Dialog.Portal>}
    </AnimatePresence>
  </Dialog.Root>;
}
