"use client";
import { usePolishMotion } from "./landing-chrome";
import { useEffect, useRef, useState, useSyncExternalStore, useId, type CSSProperties } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { ArrowLeft, BookOpen, FileSearch } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { motionTokens, counterTiming } from "@/lib/motion";
import { citationVerdict, loadReport, matchesFilter, referenceVerdict, reportCounts, verifiedEvidence, type Filter, type Report } from "@/lib/report";

import { ReaderSettingsButton } from "./reader-settings";
import { verdicts, VerdictBadge } from "@/components/verdict-badge";
import { EvidencePanel } from "@/components/evidence-panel";
import { getFlag, subscribeFlag, updateFlag } from "@/lib/evidence";
import { PeerReview } from "./peer-review";
import { applyReviewEvent, reviewState } from "@/lib/review";
import { decodeEvent } from "@/lib/job-stream";
import { loadSharedReport } from "@/lib/sharing";
import { ReportActions } from "./report-actions";
import { HiddenText } from "./hidden-text";
import dynamic from "next/dynamic";
import { reportTokens } from "@/lib/report-tokens";
import { ReportChecks } from "./report-checks";
import { ReportCompactHeader, ReportSkeleton, ReportState, ReportTab } from "./report-chrome";
import { LandingChrome } from "./landing-chrome";

const ClaimGraph = dynamic(() => import("@/components/claim-graph").then(m => m.ClaimGraph), { ssr: false, loading: () => <ReportSkeleton label="Loading claim graph" /> });
const getTab = () => new URLSearchParams(window.location.search).get("tab") || "Report";
const counters = ["References", "Not found", "DOI mismatch", "Retracted", "Partially supported", "Needs review"];
const tabs = ["Report", "Peer review", "Claim graph"];
const filters: Filter[] = ["All", "Problems only", "Needs review"];

export function ReportReader({ id, shared = false, onOpenEvidence }: { id: string; shared?: boolean; onOpenEvidence?: (citationId: string) => void }) {
  const [report, setReport] = useState<Report | null>(null), [loading, setLoading] = useState(true), [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<Filter>("All"), [selected, setSelected] = useState("");
  const [located, setLocated] = useState("");
  const view = useSyncExternalStore(subscribeFlag, getTab, () => "Report");
  function setTab(name: string) {
    if (getTab() === name) return;
    const url = new URL(window.location.href);
    if (name === "Report") url.searchParams.delete("tab"); else url.searchParams.set("tab", name);
    window.history.pushState(null, "", url); window.dispatchEvent(new PopStateEvent("popstate"));
  }
  function flash(row: HTMLElement) {
    row.removeAttribute("data-flash");
    void row.offsetWidth;
    row.dataset.flash = "true";
  }
  const tabId = useId();
  const [compact, setCompact] = useState(false);
  const [expired, setExpired] = useState(false);
  const reader = useRef<HTMLDivElement>(null), sources = useRef<HTMLDivElement>(null), reduced = usePolishMotion();
  const flag = useSyncExternalStore(subscribeFlag, getFlag, () => "");
  const paper = report?.paper, citations = paper?.citations ?? [], references = paper?.references ?? [];
  const visibleCitations = report ? citations.filter(c => matchesFilter([citationVerdict(report, c)], filter)) : [];
  const filteredReferences = report ? references.filter(r => matchesFilter([referenceVerdict(report, r.id), ...citations.filter(c => c.reference_id === r.id).map(c => citationVerdict(report, c))], filter)) : [];
  const sentences = (paper?.sentences ?? []).filter(s => filter === "All" || visibleCitations.some(c => c.sentence_ids?.includes(s.id)));
  const sections = Array.from(new Set(sentences.map(s => s.section || "Paper text")));
  const counts = report ? reportCounts(report) : counters.map(() => 0);
  const peerAvailable = loading || !!report && reviewState(report).present;
  const tab = !tabs.includes(view) || (view === "Peer review" && !peerAvailable) || (view === "Claim graph" && report?.claim_map == null) ? "Report" : view;

  useEffect(() => {
    const abort = new AbortController();
    let stream: EventSource | undefined;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      const result = shared ? await loadSharedReport(id, abort.signal) : { report: await loadReport(id, abort.signal), expired: false };
      const data = result.report;
      if (abort.signal.aborted) return;
      setExpired(result.expired);
      setReport(data); setLoading(false);
      if (!shared && (data?.status === "RUNNING" || data?.status === "QUEUED")) {
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
  }, [id, attempt, shared]);

  useEffect(() => {
    if (tab !== "Report" || !located) return;
    const frame = requestAnimationFrame(() => {
      const row = document.getElementById(located);
      if (row) { row.focus({ preventScroll: true }); flash(row); }
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
      flash(next); next.focus({ preventScroll: true }); next.scrollIntoView({ block: "center", behavior: reduced ? "instant" : "smooth" });
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

  function openGraphEvidence(citationId: string) {
    setTab("Report"); setFilter("All"); setLocated("");
    requestAnimationFrame(() => {
      const row = document.querySelector<HTMLElement>(`[data-citation-id="${CSS.escape(citationId)}"]`);
      if (row) { flash(row); row.scrollIntoView({ block: "center", behavior: reduced ? "instant" : "smooth" }); }
      openEvidence(citationId);
    });
  }

  return <main id="main" className="report-root mx-auto max-w-6xl px-5 py-8 md:px-10 md:py-10">
    <style>{reportTokens}</style>
    <LandingChrome report />
    {report && <ReportCompactHeader title={paper?.title || "Your paper review"} onVisibilityChange={setCompact} />}
    <div className="flex min-h-10 flex-wrap items-center justify-between gap-4"><Link href="/" className="inline-flex items-center gap-2 text-xs text-muted-foreground"><ArrowLeft size={14} /> Back to VerRes</Link>{report && <div className={compact ? "report-floating-actions" : undefined}><div className="flex items-center gap-2"><ReaderSettingsButton /><ReportActions id={id} shared={shared} /></div></div>}</div>
    <section aria-label="Report summary" className="report-summary mt-7 overflow-hidden border bg-white">
      <div className="p-6 md:px-10 md:py-10"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-[10px] tracking-[.2em] text-muted-foreground uppercase">{shared ? "Shared report" : "Pre-submission report"}</p>{report && <span className="inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1 text-[10px] text-muted-foreground"><FileSearch size={12} aria-hidden />{["RUNNING", "QUEUED"].includes(report.status) ? "Review in progress" : report.status === "COMPLETE" ? "Review complete" : "Needs review"}</span>}</div>
        <h1 className="mt-5 max-w-4xl font-serif text-[32px] leading-[1.15] tracking-[-.025em] md:text-[46px]">{paper?.title || (loading ? "Gathering your report…" : "Your paper review")}</h1>
        {!!paper?.authors?.length && <p className="mt-3 text-xs text-muted-foreground">{paper.authors.join(" · ")}</p>}
        <p className="mt-4 text-xs leading-6 text-muted-foreground">Every finding links to its evidence. Start with the flagged claims, then follow the evidence.</p>
      </div>
      <dl className="grid grid-cols-3 border-t md:grid-cols-6">{counters.map((label, i) => <div key={label} className="stat-tile border-r border-b px-4 py-5 nth-3:border-r-0 nth-last-[-n+3]:border-b-0 md:border-b-0 md:px-6 md:nth-3:border-r md:last:border-r-0"><dd aria-label={report ? `${counts[i]} ${label.toLowerCase()}` : undefined} className="text-[28px] font-medium tracking-tight tabular-nums">{loading ? <span aria-hidden className="report-skeleton block h-8 w-8" /> : !report ? <span aria-label="Unavailable">—</span> : <NumberFlow aria-hidden value={counts[i]} animated={!reduced} transformTiming={counterTiming} spinTiming={counterTiming} opacityTiming={{ duration: 180, easing: "ease-out" }} />}</dd><dt className="mt-1 text-[10px] text-muted-foreground">{label}</dt></div>)}</dl>
    </section>
    {report && <ReportChecks report={report} />}
    <Tabs activationMode="manual" value={tab} onValueChange={setTab} className="mt-7 gap-6">
      <TabsList aria-label="Report views" variant="line" className={`report-tabs sticky z-20 h-14 w-full justify-start gap-1 rounded-none border-b bg-background py-3 sm:gap-5 ${compact ? "report-tabs-compact" : ""}`}>{tabs.filter(name => (name !== "Peer review" || peerAvailable) && (name !== "Claim graph" || report?.claim_map != null)).map(name => <TabsTrigger key={name} id={`${tabId}-tab-${name.replaceAll(" ", "-")}`} aria-controls={`${tabId}-panel-${name.replaceAll(" ", "-")}`} value={name} className="min-h-9 flex-none px-2 text-xs sm:text-sm">{name}{tab === name && <motion.span aria-hidden className="tab-indicator" layoutId={`report-tab-${id}`} transition={reduced ? { duration: 0 } : motionTokens.layout} />}</TabsTrigger>)}</TabsList>
      <AnimatePresence mode="popLayout" initial={false}><ReportTab key={tab}>
      {tab === "Report" && <TabsContent forceMount id={`${tabId}-panel-Report`} aria-labelledby={`${tabId}-tab-Report`} value="Report">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><div role="group" aria-label="Filter findings" className="flex rounded-lg border bg-white p-1">{filters.map(name => <button key={name} type="button" aria-pressed={filter === name} onClick={() => setFilter(name)} className={`rounded-md px-3 py-2 text-[11px] ${filter === name ? "bg-secondary font-medium" : "text-muted-foreground"}`}>{name}</button>)}</div><p className="text-[10px] text-muted-foreground"><kbd>j</kbd> / <kbd>k</kbd> flags · <kbd>Enter</kbd> evidence</p></div>
        {loading && <ReportSkeleton />}
        {!loading && !report && <div role="alert"><ReportState title={expired ? "This report link has closed." : "We couldn’t finish this review."} action={expired ? undefined : "Try again"} onAction={() => setAttempt(n => n + 1)}><VerdictBadge /><p className="mt-3">{expired ? "This link expired or was revoked" : "The report could not be loaded. The check is incomplete."}</p></ReportState></div>}
        {report && <>
          <HiddenText findings={report.hidden_text} />
          {(report.reason || report.status === "CHECK_INCOMPLETE" || paper?.needs_review_reason) && <div role="status" className="mb-5 rounded-xl border bg-white p-4 text-xs leading-6"><VerdictBadge /> <span>{report.reason || paper?.needs_review_reason || "Some checks could not be completed. Inspect the available evidence."}</span></div>}
          <div ref={reader} className="grid items-start gap-7 xl:grid-cols-[minmax(0,1fr)_290px]">
            <article aria-label="Paper text" className="report-card min-w-0 border bg-white py-7 pr-6 pl-10 sm:px-12 sm:py-10"><div className="mb-8 flex items-center justify-between border-b pb-4"><h2 className="flex items-center gap-2 text-xs font-medium"><BookOpen size={15} /> The paper</h2><span className="text-[10px] text-muted-foreground">{sentences.length} sentence{sentences.length === 1 ? "" : "s"}</span></div>
              {!sentences.length && <ReportState title={paper?.sentences?.length ? "No findings in this view." : shared ? "A shared view of the evidence." : "Paper text unavailable."}><p>{paper?.sentences?.length ? "No findings match this filter." : shared ? "Full paper text is omitted from shared reports. Inspect the claim evidence in Sources & evidence." : "Paper text is unavailable. Needs review."}</p></ReportState>}
              {sections.map(section => <section key={section} className="mb-8 last:mb-0"><h3 className="mb-4 text-[10px] tracking-[.15em] text-muted-foreground uppercase">{section}</h3>{sentences.filter(s => (s.section || "Paper text") === section).map(s => {
                const markers = visibleCitations.filter(c => c.sentence_ids?.includes(s.id));
                const priority = ["RETRACTED", "NOT_FOUND", "DOI_MISMATCH", "CONTRADICTED", "NOT_SUPPORTED", "PARTIALLY_SUPPORTED", "NEEDS_REVIEW", "SUPPORTED"];
                const verdict = markers.map(c => citationVerdict(report, c)).sort((a, b) => priority.indexOf(a) - priority.indexOf(b))[0];
                const tint = verdict ? verdicts[verdict][1] : undefined;
                return <p key={s.id} id={`sentence-${s.id}`} tabIndex={-1} data-highlighted={located === `sentence-${s.id}`} data-sentence-id={s.id} data-first-reference={markers[0]?.reference_id} className="reader-paragraph mb-6 font-serif last:mb-0"><span className="paragraph-number" aria-hidden>{String((paper?.sentences?.findIndex(p => p.id === s.id) ?? 0) + 1).padStart(2, "0")}</span><span data-underline={markers.length ? true : undefined} className={markers.length ? "cited-text" : undefined} style={{ "--verdict-color": tint } as CSSProperties}>{s.text}</span>{markers.map(c => {
                  const verdict = citationVerdict(report, c), [label, color, Icon] = verdicts[verdict];
                  const number = references.findIndex(r => r.id === c.reference_id) + 1;
                  return <sup key={c.id} className="ml-1 inline-block font-sans"><button type="button" id={`citation-${c.id}`} data-highlighted={located === `citation-${c.id}`} data-citation-id={c.id} data-flag={verdict !== "SUPPORTED"} aria-label={`Citation ${number}: ${label}. Open evidence`} aria-describedby={`preview-${c.id}`} onClick={() => openEvidence(c.id)} onFocus={() => setSelected(c.id)} className="citation-mark relative inline-flex min-h-7 min-w-7 items-center justify-center gap-0.5 rounded border px-1 align-middle text-[10px]" style={{ color: verdict === "PARTIALLY_SUPPORTED" ? "var(--foreground)" : color, borderColor: color }}><Icon size={10} style={{ color }} aria-hidden />{number || "?"}<span id={`preview-${c.id}`} role="tooltip" className="citation-preview"><span className="mb-2 block font-medium">{references.find(r => r.id === c.reference_id)?.title || "Untitled source"}</span><span className="mb-2 flex items-center gap-1"><Icon size={12} aria-hidden />{label}</span>{verifiedEvidence(report, c)[0]?.quote || "A verified source quote is unavailable. Needs review."}<span className="mt-2 block text-[10px] text-muted-foreground">Select to inspect the evidence →</span></span></button></sup>;
                })}</p>;
              })}<div className="mt-8 border-t pt-5"><h4 className="mb-3 text-[9px] tracking-[.12em] text-muted-foreground uppercase">Sources in this section</h4><div className="flex flex-wrap gap-2">{references.filter(r => visibleCitations.some(c => c.reference_id === r.id && sentences.some(s => (s.section || "Paper text") === section && c.sentence_ids?.includes(s.id)))).map(r => <button key={r.id} type="button" onClick={() => { const c = visibleCitations.find(c => c.reference_id === r.id && sentences.some(s => (s.section || "Paper text") === section && c.sentence_ids?.includes(s.id))); if (c) openEvidence(c.id); }} className="max-w-full rounded-md bg-background px-2.5 py-1.5 text-left text-[10px] leading-4"><span className="mr-1 font-medium">[{references.indexOf(r) + 1}]</span>{r.title || r.raw_text}</button>)}</div></div></section>)}
            </article>
            <aside aria-label="Sources" className="min-w-0 xl:sticky xl:top-64"><div className="mb-3 flex items-center justify-between px-1"><h2 className="text-xs font-medium">Sources & evidence</h2><span className="text-[10px] text-muted-foreground">Synced to the paper</span></div><div ref={sources} className="relative space-y-3 xl:max-h-[calc(100dvh-280px)] xl:overflow-y-auto xl:pr-1">
              {filteredReferences.map(r => {
                const existence = report.existence?.find(e => e.reference_id === r.id), retraction = report.retractions?.find(e => e.reference_id === r.id), source = report.sources?.find(e => e.reference_id === r.id);
                const cited = citations.filter(c => c.reference_id === r.id), active = cited.some(c => c.id === selected);
                return <section key={r.id} data-source-id={r.id} className={`report-card border bg-white p-5 ${active ? "outline outline-1 outline-foreground/30" : ""}`}><div className="flex items-start justify-between gap-3"><h3 className="text-sm leading-6"><span className="mr-2 text-[10px] text-muted-foreground">[{references.indexOf(r) + 1}]</span>{r.title || r.raw_text}</h3><span className="shrink-0 pt-1 text-[10px] text-muted-foreground">cited {cited.length}x</span></div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{r.year ?? "Year unavailable"} · {r.raw_text}</p><div className="mt-3 flex flex-wrap gap-2">{Array.from(new Set(cited.map(c => citationVerdict(report, c)))).map(status => <VerdictBadge key={status} status={status} />)}</div><div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground"><span>Reference</span><VerdictBadge status={existence?.status} /><span>Retraction</span><VerdictBadge status={retraction?.status} /></div>
                  <p className="mt-3 flex items-center gap-1.5 text-[10px] text-muted-foreground"><FileSearch size={12} />{source?.status === "AVAILABLE" ? ({ FULL_TEXT: "Full text", ABSTRACT_ONLY: "Abstract only", METADATA_ONLY: "Metadata only" }[source.evidence_level] || "Evidence unavailable") : "Evidence unavailable"}</p>
                  <details className="mt-4 border-t pt-3 text-xs leading-6"><summary className="cursor-pointer text-muted-foreground">Evidence & reason</summary>{existence?.status === "NOT_FOUND" && <p>Not found in Crossref, OpenAlex or arXiv.</p>}<p>{existence?.reason || "Existence check incomplete. Needs review."}</p><p>{retraction?.reason || "Retraction check incomplete. Needs review."}</p><p>{source?.reason}</p>{Array.from(new Set([...(existence?.receipt_urls ?? []), ...(retraction?.notice_urls ?? [])])).filter(url => /^https?:\/\//i.test(url)).map(url => <a key={url} href={url} target="_blank" rel="noreferrer" className="block break-all underline">{url}</a>)}
                    {cited.map(c => <div key={c.id} className="mt-3 border-t pt-3"><button onClick={() => openEvidence(c.id)} aria-label={`Open evidence for ${c.id}`}><VerdictBadge status={citationVerdict(report, c)} /></button><p>{report.support?.find(s => s.citation_id === c.id)?.reason || "Claim support check incomplete. Needs review."}</p>{verifiedEvidence(report, c).map((e, i) => <blockquote key={i} className="mt-2 border-l-2 pl-3 font-serif">“{e.quote}” <span className="font-sans text-[10px] text-muted-foreground">{e.passage_id}</span></blockquote>)}</div>)}
                  </details>
                </section>;
              })}
              {!filteredReferences.length && <ReportState title={references.length ? "No sources match this view." : "No sources extracted."} action={references.length ? "Show all findings" : undefined} onAction={() => setFilter("All")}><p>{references.length ? "Try the complete paper view to inspect all available evidence." : "No references were extracted. Needs review."}</p></ReportState>}
            </div></aside>
          </div>
          <p aria-live="polite" className="sr-only">{selected ? `Evidence selected for ${selected}` : ""}</p>
        </>}
      </TabsContent>}
      {tab === "Peer review" && <TabsContent forceMount id={`${tabId}-panel-Peer-review`} aria-labelledby={`${tabId}-tab-Peer-review`} value="Peer review"><PeerReview report={report} onLocate={target => { setFilter("All"); setLocated(target); setTab("Report"); }} /></TabsContent>}
      {tab === "Claim graph" && report?.claim_map && <TabsContent forceMount id={`${tabId}-panel-Claim-graph`} aria-labelledby={`${tabId}-tab-Claim-graph`} value="Claim graph"><ClaimGraph report={report} onOpenEvidence={openGraphEvidence} /></TabsContent>}
      </ReportTab></AnimatePresence>
    </Tabs>
    {report && <EvidencePanel report={report} citationId={flag} onClose={() => updateFlag("")} shared={shared} />}
  </main>;
}
