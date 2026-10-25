"use client";
import { useRef, useState } from "react";
import { Dialog } from "radix-ui";
import { ArrowUpRight, FileSearch, Users, X } from "lucide-react";
import { VerdictBadge } from "@/components/verdict-badge";
import { evidenceDetails } from "@/lib/evidence";
import type { Report } from "@/lib/report";
import { Provenance } from "./provenance";

export function EvidencePanel({ report, citationId, onClose, shared = false }: { report: Report; citationId: string; onClose: () => void; shared?: boolean }) {
  const returnFocus = useRef<HTMLElement | null>(null);
  const [lastCitation, setLastCitation] = useState(citationId);
  if (citationId && citationId !== lastCitation) setLastCitation(citationId);
  const citation = report.paper?.citations?.find(c => c.id === (citationId || lastCitation));
  const data = citation && evidenceDetails(report, citation);
  const reference = report.paper?.references?.find(r => r.id === citation?.reference_id);
  const quotes = data && shared && !data.source?.passages?.length ? data.support?.evidence ?? [] : data?.quotes ?? [];
  return <Dialog.Root open={!!citationId && !!citation} onOpenChange={open => { if (!open) onClose(); }}>
      {citation && data && <Dialog.Portal>
        <Dialog.Overlay className="report-overlay evidence-backdrop fixed inset-0 z-50" />
        <Dialog.Content onOpenAutoFocus={() => { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; }} onCloseAutoFocus={event => {
          event.preventDefault();
          const target = returnFocus.current;
          if (target?.isConnected && target !== document.body) target.focus({ preventScroll: true });
          else document.querySelector<HTMLButtonElement>(`[data-citation-id="${CSS.escape(citationId || lastCitation)}"]`)?.focus({ preventScroll: true });
        }} className="report-overlay evidence-panel fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l bg-background sm:max-w-[820px]">
            <header className="flex shrink-0 items-center justify-between border-b bg-white px-6 py-5 sm:rounded-tl-xl sm:px-8">
              <div><Dialog.Title className="font-serif text-2xl">Evidence details</Dialog.Title><Dialog.Description className="mt-1 text-xs text-muted-foreground">Follow the claim to its source.</Dialog.Description></div>
              <Dialog.Close aria-label="Close evidence" className="rounded-md border p-2.5"><X size={18} /></Dialog.Close>
            </header>
            <div key={citation.id} className="min-h-0 overflow-y-auto overscroll-contain px-6 py-6 sm:px-8">
              <div className="flex flex-wrap items-center gap-2"><VerdictBadge status={data.verdict} />{data.mismatches.map((m, i) => <span key={i} className="rounded-md border bg-white px-2 py-1 text-xs text-muted-foreground">{m.replaceAll("_", " ").toLowerCase()}</span>)}</div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span>Reference</span><VerdictBadge status={report.existence?.find(e => e.reference_id === citation.reference_id)?.status} /><span>Retraction</span><VerdictBadge status={report.retractions?.find(e => e.reference_id === citation.reference_id)?.status} /></div>
              {data.needsReview && <p role="status" className="mt-4 rounded-md border bg-white p-4 text-sm font-medium leading-6">{data.needsReview}</p>}
              <p className="source-identifier">{reference?.doi ? `DOI ${reference.doi}` : reference?.arxiv_id ? `arXiv:${reference.arxiv_id}` : "Source identifier unavailable"}</p><div className="mt-6 grid items-start gap-4 md:grid-cols-2"><section className="rounded-md border bg-white p-5">
                <h3 className="mb-3 text-xs font-medium  text-muted-foreground">Your paper says</h3>
                {(report.paper?.sentences?.filter(s => citation.sentence_ids?.includes(s.id)) ?? []).map(s => {
                  const start = citation.claim_text ? s.text.indexOf(citation.claim_text) : -1;
                  return <p key={s.id} className="font-serif text-lg leading-8">{start < 0 ? s.text : <>{s.text.slice(0, start)}<mark className="matched-span">{citation.claim_text}</mark>{s.text.slice(start + citation.claim_text.length)}</>}</p>;
                })}
                {!report.paper?.sentences?.some(s => citation.sentence_ids?.includes(s.id)) && <p className="text-sm text-muted-foreground">Citing sentence unavailable. Needs review.</p>}
                {!!citation.claim_text && !report.paper?.sentences?.some(s => citation.sentence_ids?.includes(s.id) && s.text.includes(citation.claim_text)) && <p className="mt-3 font-serif text-lg"><mark className="matched-span">{citation.claim_text}</mark></p>}
              </section>
              <section className="rounded-md border bg-white p-5">
                <h3 className="mb-4 text-xs font-medium  text-muted-foreground">The source says</h3>
                {quotes.map((e, i) => <figure key={i} className="mt-4 first:mt-0">
                  <blockquote className="font-serif text-lg leading-8">“<span data-quote-sweep className="matched-span">{e.quote}</span>”</blockquote>
                  <figcaption className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="inline-flex items-center gap-1 rounded-md border px-2 py-1"><FileSearch size={12} />{data.source?.evidence_level === "FULL_TEXT" ? "Full text" : data.source?.evidence_level === "ABSTRACT_ONLY" ? "Abstract only" : "Metadata only"}</span><span>{data.quotes.includes(e) ? "Verified verbatim" : "Reported quote · source passages omitted"} · {e.passage_id}</span></figcaption>
                  <Provenance label="Quote" value={e} />
                </figure>)}
                {!data.quotes.length && <p className="text-sm leading-6 text-muted-foreground">{quotes.length ? "Source passages are omitted from shared reports. Quotes cannot be verified here. Needs review." : "No verified source quote available. Needs review."}</p>}
              </section>
              </div>{!!data.reasons.length && <><h3 className="mt-7 text-xs font-medium  text-muted-foreground">Why this verdict</h3>
              {data.reasons.map((text, i) => <p key={text} className={i ? "mt-3 text-xs leading-6 text-muted-foreground" : "mt-3 text-sm leading-6"}>{text}</p>)}</>}
              {data.agreement && <p className="mt-4 inline-flex items-center gap-2 rounded-md border bg-white px-3 py-2 text-xs text-muted-foreground"><Users size={14} />{data.agreement}</p>}
              <Provenance label="Source" value={data.source && { ...data.source, source_url: data.source.source_url || data.source.url }} />
              <Provenance label="Claim check" value={data.support} />
              <Provenance label="Citation check" value={report.existence?.find(e => e.reference_id === citation.reference_id)} />
              <Provenance label="Retraction check" value={report.retractions?.find(e => e.reference_id === citation.reference_id)} />
              <nav aria-label="Evidence links" className="mt-6 space-y-2 border-t pt-5">{data.links.map(({ href, label }) => <a key={href} href={href} target="_blank" rel="noreferrer" className="flex items-start justify-between gap-3 rounded-md border bg-white p-3 text-xs"><span className="min-w-0"><span className="font-medium">{label}</span><span className="mt-1 block break-all text-xs text-muted-foreground">{href}</span></span><ArrowUpRight size={14} className="shrink-0" /></a>)}{!data.links.length && <p className="text-xs text-muted-foreground">No evidence links available.</p>}</nav>
            </div>
        </Dialog.Content>
      </Dialog.Portal>}
  </Dialog.Root>;
}
