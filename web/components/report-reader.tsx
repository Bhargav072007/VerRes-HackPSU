"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { ArrowLeft, BookOpen, FileSearch } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { motionTokens } from "@/lib/motion";
import { citationVerdict, loadReport, matchesFilter, referenceVerdict, reportCounts, verifiedEvidence, type Filter, type Report } from "@/lib/report";

import { verdicts, VerdictBadge } from "@/components/verdict-badge";
import { EvidencePanel } from "@/components/evidence-panel";
import { getFlag, subscribeFlag, updateFlag } from "@/lib/evidence";
import { PeerReview } from "./peer-review";
import { applyReviewEvent, reviewState } from "@/lib/review";
import { decodeEvent } from "@/lib/job-stream";

const counters = ["References", "Not found", "DOI mismatch", "Retracted", "Overstated", "Needs review"];
const tabs = ["Report", "Peer review", "Claim graph", "Integrity"];
const filters: Filter[] = ["All", "Problems only", "Needs review"];

export function ReportReader({ id, onOpenEvidence }: { id: string; onOpenEvidence?: (citationId: string) => void }) {
  const [report, setReport] = useState<Report | null>(null), [loading, setLoading] = useState(true), [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<Filter>("All"), [view, setTab] = useState("Report"), [selected, setSelected] = useState("");
  const [located, setLocated] = useState("");
  const reader = useRef<HTMLDivElement>(null), sources = useRef<HTMLDivElement>(null), reduced = useReducedMotion();
  const flag = useSyncExternalStore(subscribeFlag, getFlag, () => "");
  const paper = report?.paper, citations = paper?.citations ?? [], references = paper?.references ?? [];
  const visibleCitations = report ? citations.filter(c => matchesFilter([citationVerdict(report, c)], filter)) : [];
  const sentences = (paper?.sentences ?? []).filter(s => filter === "All" || visibleCitations.some(c => c.sentence_ids?.includes(s.id)));
  const sections = Array.from(new Set(sentences.map(s => s.section || "Paper text")));
  const counts = report ? reportCounts(report) : counters.map(() => 0);
  const peerAvailable = loading || !!report && reviewState(report).present;
  const tab = view === "Peer review" && !peerAvailable ? "Report" : view;

  useEffect(() => {
    const abort = new AbortController();
    let stream: EventSource | undefined;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      const data = await loadReport(id, abort.signal);
      if (abort.signal.aborted) return;
      setReport(data); setLoading(false);
      if (data?.status === "RUNNING" || data?.status === "QUEUED") {
        if (!stream && process.env.NEXT_PUBLIC_MOCK !== "1") {
          const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
          stream = new EventSource(`${base}/jobs/${encodeURIComponent(id)}/events`);
          for (const type of ["review", "review_summary", "hidden_text", "stage", "done"]) stream.addEventListener(type, message => {
            if (!(message instanceof MessageEvent)) return;
            try {
              const event = decodeEvent({ type, seq: Number(message.lastEventId), payload: JSON.parse(message.data) });
              if (event) setReport(current => current ? applyReviewEvent(current, event) : current);
              if (event?.type === "done") { stream?.close(); clearTimeout(timer); void refresh(); }
            } catch { /* Polling recovers unreadable events without blocking the report. */ }
          });
        }
        timer = setTimeout(refresh, 2000);
      } else stream?.close();
    }
    void refresh();
    return () => { abort.abort(); stream?.close(); clearTimeout(timer); };
  }, [id, attempt]);

  useEffect(() => {
    if (tab !== "Report" || !located) return;
    const frame = requestAnimationFrame(() => {
      const row = document.getElementById(located);
      row?.focus({ preventScroll: true });
      row?.scrollIntoView({ block: "center", behavior: reduced ? "instant" : "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [tab, located, reduced]);

  useEffect(() => {
    if (tab !== "Report") return;
    const navigate = (event: KeyboardEvent) => {
      if (document.querySelector('[role="dialog"]') || event.ctrlKey || event.metaKey || event.altKey || event.target instanceof HTMLElement && event.target.closest("input, textarea, select, [contenteditable=true]")) return;
      if (event.key !== "j" && event.key !== "k") return;
      const flags = Array.from(reader.current?.querySelectorAll<HTMLButtonElement>("[data-flag=true]") ?? []);
      if (!flags.length) return;
      event.preventDefault();
      const current = flags.indexOf(document.activeElement as HTMLButtonElement);
      const next = flags[(current < 0 ? event.key === "j" ? 0 : flags.length - 1 : current + (event.key === "j" ? 1 : -1) + flags.length) % flags.length];
      next.focus({ preventScroll: true }); next.scrollIntoView({ block: "center", behavior: reduced ? "instant" : "smooth" });
    };
    window.addEventListener("keydown", navigate);
    return () => window.removeEventListener("keydown", navigate);
  }, [tab, reduced]);

  useEffect(() => {
    const pane = sources.current;
    if (!pane || !window.matchMedia("(min-width: 1024px)").matches) return;
    const observer = new IntersectionObserver(entries => {
      const sentence = entries.find(e => e.isIntersecting)?.target;
      const reference = sentence?.getAttribute("data-first-reference");
      const card = Array.from(pane.querySelectorAll<HTMLElement>("[data-source-id]")).find(n => n.dataset.sourceId === reference);
      if (card) pane.scrollTo({ top: pane.scrollTop + card.getBoundingClientRect().top - pane.getBoundingClientRect().top, behavior: "instant" });
    }, { rootMargin: "-10% 0px -65% 0px" });
    reader.current?.querySelectorAll("[data-first-reference]").forEach(s => observer.observe(s));
    return () => observer.disconnect();
  }, [report, filter, tab]);

  function openEvidence(citationId: string) {
    setSelected(citationId);
    updateFlag(citationId);
    onOpenEvidence?.(citationId);
    if (!onOpenEvidence) window.dispatchEvent(new CustomEvent("verres:open-evidence", { detail: { citationId } }));
  }

  return <main id="main" className="mx-auto max-w-6xl px-5 py-8 md:px-10 md:py-10">
    <Link href="/" className="inline-flex items-center gap-2 text-xs text-muted-foreground"><ArrowLeft size={14} /> Back to VerRes</Link>
    <section aria-label="Report summary" className="mt-7 overflow-hidden rounded-xl border bg-white">
      <div className="p-6 md:p-8"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-[10px] tracking-[.2em] text-muted-foreground uppercase">Pre-submission report</p>{report && <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><FileSearch size={14} />{["RUNNING", "QUEUED"].includes(report.status) ? "Review in progress" : "Review complete"}</span>}</div>
        <h1 className="mt-4 max-w-3xl font-serif text-[28px] leading-tight md:text-4xl">{paper?.title || (loading ? "Gathering your report…" : "Your paper review")}</h1>
        {!!paper?.authors?.length && <p className="mt-3 text-xs text-muted-foreground">{paper.authors.join(" · ")}</p>}
        <p className="mt-4 text-xs leading-6 text-muted-foreground">Every finding has a receipt. Start with the flagged claims, then follow the evidence.</p>
      </div>
      <dl className="grid grid-cols-3 border-t md:grid-cols-6">{counters.map((label, i) => <div key={label} className="border-r px-4 py-5 last:border-r-0 md:px-6"><dd aria-label={`${counts[i]} ${label.toLowerCase()}`} className="text-2xl font-medium tabular-nums"><NumberFlow aria-hidden value={counts[i]} animated={!reduced} transformTiming={{ duration: 350, easing: "ease-out" }} spinTiming={{ duration: 350, easing: "ease-out" }} opacityTiming={{ duration: 180, easing: "ease-out" }} /></dd><dt className="mt-1 text-[10px] text-muted-foreground">{label}</dt></div>)}</dl>
    </section>
    <Tabs value={tab} onValueChange={setTab} className="mt-7 gap-6">
      <TabsList aria-label="Report views" variant="line" className="w-full justify-start gap-1 border-b pb-3 sm:gap-5">{tabs.filter(name => name !== "Peer review" || peerAvailable).map(name => <TabsTrigger key={name} value={name} className="flex-none px-1 text-xs sm:px-2 sm:text-sm">{name}</TabsTrigger>)}</TabsList>
      <TabsContent value="Report">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><div role="group" aria-label="Filter findings" className="flex rounded-lg border bg-white p-1">{filters.map(name => <button key={name} type="button" aria-pressed={filter === name} onClick={() => setFilter(name)} className={`rounded-md px-3 py-2 text-[11px] ${filter === name ? "bg-secondary font-medium" : "text-muted-foreground"}`}>{name}</button>)}</div><p className="text-[10px] text-muted-foreground"><kbd>j</kbd> / <kbd>k</kbd> flags · <kbd>Enter</kbd> evidence</p></div>
        {loading && <p role="status" className="rounded-xl border bg-white p-8 text-sm">Loading your report…</p>}
        {!loading && !report && <div role="alert" className="rounded-xl border bg-white p-8"><VerdictBadge /><p className="my-4 text-sm">The report could not be loaded. The check is incomplete.</p><button className="rounded-md border px-4 py-2 text-xs" onClick={() => setAttempt(n => n + 1)}>Try again</button></div>}
        {report && <>
          {(report.reason || report.status === "CHECK_INCOMPLETE" || paper?.needs_review_reason) && <div role="status" className="mb-5 rounded-xl border bg-white p-4 text-xs leading-6"><VerdictBadge /> <span>{report.reason || paper?.needs_review_reason || "Some checks could not be completed. Inspect the available receipts."}</span></div>}
          <div ref={reader} className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <article aria-label="Paper text" className="min-w-0 rounded-xl border bg-white p-6 md:p-8"><div className="mb-8 flex items-center justify-between border-b pb-4"><h2 className="flex items-center gap-2 text-xs font-medium"><BookOpen size={15} /> The paper</h2><span className="text-[10px] text-muted-foreground">{sentences.length} sentence{sentences.length === 1 ? "" : "s"}</span></div>
              {!sentences.length && <p className="text-sm leading-6 text-muted-foreground">{paper?.sentences?.length ? "No findings match this filter." : "Paper text is unavailable. Needs review."}</p>}
              {sections.map(section => <section key={section} className="mb-8 last:mb-0"><h3 className="mb-4 text-[10px] tracking-[.15em] text-muted-foreground uppercase">{section}</h3>{sentences.filter(s => (s.section || "Paper text") === section).map(s => {
                const markers = visibleCitations.filter(c => c.sentence_ids?.includes(s.id));
                const underline = markers.some(c => ["NOT_SUPPORTED", "CONTRADICTED"].includes(citationVerdict(report, c)));
                return <p key={s.id} id={`sentence-${s.id}`} tabIndex={-1} data-highlighted={located === `sentence-${s.id}`} data-sentence-id={s.id} data-first-reference={markers[0]?.reference_id} className="mb-5 scroll-mt-12 font-serif text-[17px] leading-7 last:mb-0 data-[highlighted=true]:bg-secondary data-[highlighted=true]:outline"><span className="relative">{s.text}{underline && <motion.span aria-hidden data-underline className="pointer-events-none absolute inset-x-0 bottom-0 border-b-2" initial={reduced ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} style={{ transformOrigin: "left", borderColor: "#b423184d" }} transition={motionTokens.fade} />}</span>{markers.map(c => {
                  const verdict = citationVerdict(report, c), [label, color, Icon] = verdicts[verdict];
                  const number = references.findIndex(r => r.id === c.reference_id) + 1;
                  return <sup key={c.id} className="ml-1 inline-block font-sans"><button type="button" id={`citation-${c.id}`} data-highlighted={located === `citation-${c.id}`} data-citation-id={c.id} data-flag={verdict !== "SUPPORTED"} aria-label={`Citation ${number}: ${label}. Open evidence`} title={`${label} · Open evidence`} onClick={() => openEvidence(c.id)} onFocus={() => setSelected(c.id)} className="relative inline-flex min-h-6 min-w-7 items-center justify-center gap-0.5 overflow-hidden rounded border px-1 align-middle text-[10px] data-[highlighted=true]:ring-2 data-[highlighted=true]:ring-foreground/40" style={{ color, borderColor: color }}><motion.span key={verdict} aria-hidden className="absolute inset-0 origin-bottom" style={{ backgroundColor: color, opacity: .1 }} initial={reduced ? false : { scaleY: 0 }} animate={{ scaleY: 1 }} transition={motionTokens.fade} /><Icon size={10} aria-hidden />{number || "?"}</button></sup>;
                })}</p>;
              })}</section>)}
            </article>
            <aside aria-label="Sources" className="min-w-0 lg:sticky lg:top-6"><div className="mb-3 flex items-center justify-between px-1"><h2 className="text-xs font-medium">Sources & receipts</h2><span className="text-[10px] text-muted-foreground">Synced to the paper</span></div><div ref={sources} className="relative space-y-3 lg:max-h-[calc(100dvh-100px)] lg:overflow-y-auto lg:pr-1">
              {references.filter(r => matchesFilter([referenceVerdict(report, r.id), ...citations.filter(c => c.reference_id === r.id).map(c => citationVerdict(report, c))], filter)).map(r => {
                const existence = report.existence?.find(e => e.reference_id === r.id), retraction = report.retractions?.find(e => e.reference_id === r.id), source = report.sources?.find(e => e.reference_id === r.id);
                const cited = citations.filter(c => c.reference_id === r.id), active = cited.some(c => c.id === selected);
                return <section key={r.id} data-source-id={r.id} className={`rounded-xl border bg-white p-5 ${active ? "outline outline-1 outline-foreground/30" : ""}`}><div className="flex items-start justify-between gap-3"><h3 className="text-sm leading-6"><span className="mr-2 text-[10px] text-muted-foreground">[{references.indexOf(r) + 1}]</span>{r.title || r.raw_text}</h3><span className="shrink-0 pt-1 text-[10px] text-muted-foreground">cited {cited.length}x</span></div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{r.year ?? "Year unavailable"} · {r.raw_text}</p><div className="mt-3 flex flex-wrap gap-2"><VerdictBadge status={existence?.status} /><VerdictBadge status={retraction?.status} /></div>
                  <p className="mt-3 flex items-center gap-1.5 text-[10px] text-muted-foreground"><FileSearch size={12} />{source?.status === "AVAILABLE" ? ({ FULL_TEXT: "Full text", ABSTRACT_ONLY: "Abstract only", METADATA_ONLY: "Metadata only" }[source.evidence_level] || "Evidence unavailable") : "Evidence unavailable"}</p>
                  <details className="mt-4 border-t pt-3 text-xs leading-6"><summary className="cursor-pointer text-muted-foreground">Receipts & reason</summary>{existence?.status === "NOT_FOUND" && <p>Not found in Crossref, OpenAlex or arXiv.</p>}<p>{existence?.reason || "Existence check incomplete. Needs review."}</p><p>{retraction?.reason || "Retraction check incomplete. Needs review."}</p><p>{source?.reason}</p>{Array.from(new Set([...(existence?.receipt_urls ?? []), ...(retraction?.notice_urls ?? [])])).filter(url => /^https?:\/\//i.test(url)).map(url => <a key={url} href={url} target="_blank" rel="noreferrer" className="block break-all underline">{url}</a>)}
                    {cited.map(c => <div key={c.id} className="mt-3 border-t pt-3"><button onClick={() => openEvidence(c.id)} aria-label={`Open evidence for ${c.id}`}><VerdictBadge status={citationVerdict(report, c)} /></button><p>{report.support?.find(s => s.citation_id === c.id)?.reason || "Claim support check incomplete. Needs review."}</p>{verifiedEvidence(report, c).map((e, i) => <blockquote key={i} className="mt-2 border-l-2 pl-3 font-serif">“{e.quote}” <span className="font-sans text-[10px] text-muted-foreground">{e.passage_id}</span></blockquote>)}</div>)}
                  </details>
                </section>;
              })}
              {!references.length && <p className="rounded-xl border bg-white p-5 text-sm text-muted-foreground">No references were extracted. Needs review.</p>}
            </div></aside>
          </div>
          <p aria-live="polite" className="sr-only">{selected ? `Evidence selected for ${selected}` : ""}</p>
        </>}
      </TabsContent>
      <TabsContent value="Peer review"><PeerReview report={report} onLocate={target => { setFilter("All"); setLocated(target); setTab("Report"); }} /></TabsContent>
      {tabs.slice(2).map(name => <TabsContent key={name} value={name} className="rounded-xl border bg-white px-6 py-14 text-center"><FileSearch size={24} className="mx-auto text-muted-foreground" /><h2 className="mt-4 font-serif text-2xl">{name}</h2><p className="mt-2 text-sm text-muted-foreground">This view is coming soon. Citation receipts are available in the Report tab.</p></TabsContent>)}
    </Tabs>
    {report && <EvidencePanel report={report} citationId={flag} onClose={() => updateFlag("")} />}
  </main>;
}
