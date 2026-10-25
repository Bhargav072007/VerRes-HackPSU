import type { JobEvent } from "./job-stream";
import type { Report } from "./report";
import { referenceChip, type HeroChip } from "./landing-data";

// The review room is a pure reading of the event log: every number on screen comes from an event that arrived.
export type LoggedEvent = JobEvent & { receivedAt: number };
export type AgentId = "parser" | "hidden" | "claims" | "resolver" | "retraction" | "source" | "verifier" | "CLAIMS" | "METHODS" | "EVIDENCE" | "chair";
export type AgentStatus = "QUEUED" | "WORKING" | "DONE" | "FLAGGED" | "NEEDS_REVIEW";
export type Agent = { id: AgentId; name: string; detail?: string; status: AgentStatus; current?: string; done: number; total: number | null; finding?: string; model?: string; reason?: string };
export type FeedRow = { seq: number; at: number; agent: AgentId; text: string; chip?: HeroChip };
export type Slot = { id: string; index: number; label: string; chip: HeroChip | null };

const panel = (s: string) => s === "review_prep" || s === "run_review_panel";
const agentDefs: { id: AgentId; name: string; detail?: string; owns: (stage: string) => boolean }[] = [
  { id: "parser", name: "Parser (GROBID)", owns: s => s === "intake" || s === "parse_pdf" },
  { id: "hidden", name: "Hidden-text scanner", owns: s => s === "hidden_text" },
  { id: "claims", name: "Claim mapper", owns: s => s === "build_claim_map" || s === "claim_map" },
  { id: "resolver", name: "Reference resolver", detail: "Crossref · OpenAlex · arXiv", owns: s => s.startsWith("existence:") },
  { id: "retraction", name: "Retraction checker", owns: s => s.startsWith("retraction:") },
  { id: "source", name: "Source retriever", owns: s => s.startsWith("source:") },
  { id: "verifier", name: "Claim verifier", owns: s => s.startsWith("support:") },
  { id: "CLAIMS", name: "Reviewer · Claims", owns: panel },
  { id: "METHODS", name: "Reviewer · Methods", owns: panel },
  { id: "EVIDENCE", name: "Reviewer · Evidence", owns: panel },
  { id: "chair", name: "Area chair", owns: s => s === "summary" },
];
const FIXED_STAGES = 8; // intake, parse_pdf, hidden_text, build_claim_map, review_prep, run_review_panel, claim_map, summary
const existenceText: Record<string, [string, HeroChip]> = { VERIFIED: ["Found", "SUPPORTED"], VERIFIED_WITH_DISCREPANCIES: ["Found, with discrepancies", "NEEDS_REVIEW"], NOT_FOUND: ["Not found in Crossref, OpenAlex, arXiv", "NOT_FOUND"], DOI_MISMATCH: ["DOI mismatch", "DOI_MISMATCH"] };
const levelText: Record<string, string> = { FULL_TEXT: "Full text", ABSTRACT_ONLY: "Abstract", METADATA_ONLY: "Metadata only" };
const clip = (text: string, n = 60) => text.length > n ? `${text.slice(0, n - 1)}…` : text;

export function deriveRoom(log: LoggedEvent[], now = Date.now()) {
  const paper = log.findLast(e => e.type === "paper")?.payload as Report["paper"] | undefined;
  const refs = paper?.references ?? [], citations = paper?.citations ?? [];
  const refIndex = (id: string) => refs.findIndex(r => r.id === id);
  const refLabel = (id: string) => { const i = refIndex(id), r = refs[i]; return i < 0 ? id : `[${i + 1}] ${r?.authors?.[0] ?? "Reference"}${r?.year ? ` ${r.year}` : ""}`; };
  const citeLabel = (id: string) => { const c = citations.find(x => x.id === id); return c ? clip(c.claim_text || "") : id; };
  const started = new Map<string, number>(), finished = new Map<string, string>(), reasons = new Map<string, string>();
  const of = <T>(type: string) => log.filter(e => e.type === type).map(e => e.payload as T);
  type R = Record<string, unknown>;
  for (const e of log) if (e.type === "stage") {
    const { stage, status, reason } = e.payload;
    if (status === "STARTED") started.set(stage, e.seq); else { finished.set(stage, status); if (status === "CHECK_INCOMPLETE") reasons.set(stage, reason || "Stage incomplete. Needs review."); }
  }
  const done = log.find(e => e.type === "done");
  const existence = of<R>("existence"), retractions = of<R>("retraction"), sources = of<R>("source"), support = of<R>("support"), reviews = of<R>("review"), hidden = of<R>("hidden_text");
  const summary = log.findLast(e => e.type === "review_summary")?.payload as { top_fixes?: string[] } | undefined;
  const claimMap = log.findLast(e => e.type === "claim_map")?.payload as { nodes?: unknown[] } | undefined;
  // A partial report from what has arrived, so slot verdicts use the same rules (and colours) as the hero and the report.
  const report = { paper, existence, retractions, sources, support } as unknown as Report;
  const totals: Partial<Record<AgentId, number | null>> = { parser: 2, hidden: 1, claims: 2, resolver: paper ? refs.length : null, retraction: paper ? refs.length : null, source: paper ? refs.length : null, verifier: paper ? citations.length : null, chair: 1 };
  const agents: Agent[] = agentDefs.map(def => {
    const mine = [...started.keys()].filter(def.owns), complete = mine.filter(s => finished.has(s)), running = mine.filter(s => !finished.has(s));
    const incomplete = mine.filter(s => finished.get(s) === "CHECK_INCOMPLETE");
    const isReviewer = def.id === "CLAIMS" || def.id === "METHODS" || def.id === "EVIDENCE";
    const total = isReviewer ? null : totals[def.id] ?? null;
    let finding: string | undefined, current: string | undefined, model: string | undefined, flagged = false;
    const last = running.at(-1), item = last?.split(":")[1];
    if (def.id === "parser" && paper) finding = `Extracted ${paper.sentences?.length ?? 0} sentences · ${refs.length} references`;
    if (def.id === "hidden" && finished.has("hidden_text")) { const flags = hidden.filter(h => h.kind !== "CHECK_INCOMPLETE").length; flagged = flags > 0; finding = flags ? `${flags} hidden-text flag${flags > 1 ? "s" : ""}` : "No hidden text found"; }
    if (def.id === "claims" && claimMap) finding = `${claimMap.nodes?.length ?? 0} claims mapped`;
    if (def.id === "resolver") { const r = existence.at(-1); if (r) finding = `${refLabel(String(r.reference_id))} · ${(existenceText[String(r.status)] ?? ["Needs review"])[0]}`; flagged = existence.some(x => x.status === "NOT_FOUND" || x.status === "DOI_MISMATCH"); if (item) current = refLabel(item); }
    if (def.id === "retraction") { const r = retractions.at(-1); if (r) finding = `${refLabel(String(r.reference_id))} · ${r.status === "RETRACTED" ? "Retracted" : r.status === "NONE" ? "No retraction found" : "Needs review"}`; flagged = retractions.some(x => x.status === "RETRACTED"); if (item) current = refLabel(item); }
    if (def.id === "source") { const r = sources.at(-1); if (r) finding = `${refLabel(String(r.reference_id))} · ${r.status === "AVAILABLE" ? levelText[String(r.evidence_level)] ?? "Source" : "Unavailable"}`; if (item) current = refLabel(item); }
    if (def.id === "verifier") { const r = support.at(-1); if (r) finding = `${citeLabel(String(r.citation_id))} · ${String(r.label).replaceAll("_", " ").toLowerCase()}`; flagged = support.some(x => x.label === "NOT_SUPPORTED" || x.label === "CONTRADICTED"); model = support.findLast(x => typeof x.model_id === "string")?.model_id as string | undefined; if (item) current = citeLabel(item); }
    if (isReviewer) { const mineReviews = reviews.filter(r => r.reviewer === def.id), major = mineReviews.filter(r => r.severity === "MAJOR").length; if (mineReviews.length) finding = `${mineReviews.length} finding${mineReviews.length > 1 ? "s" : ""} · ${major} major`; model = mineReviews.findLast(r => typeof r.model_id === "string")?.model_id as string | undefined; if (running.length) current = running.includes("run_review_panel") ? "Reading the manuscript" : "Preparing the panel"; }
    if (def.id === "chair") { if (running.length) current = "Writing the meta-review"; if (summary) finding = `${summary.top_fixes?.length ?? 0} priorities for the author`; }
    const count = isReviewer ? reviews.filter(r => r.reviewer === def.id).length : complete.length;
    let status: AgentStatus = incomplete.length ? "NEEDS_REVIEW" : running.length || (mine.length && total != null && complete.length < total && !done) ? "WORKING" : mine.length || done ? "DONE" : "QUEUED";
    if (status === "DONE" && flagged) status = "FLAGGED";
    return { id: def.id, name: def.name, detail: def.detail, status, current: status === "WORKING" ? current : undefined, done: count, total, finding, model, reason: incomplete.length ? reasons.get(incomplete.at(-1)!) : undefined };
  });
  const feed: FeedRow[] = [];
  for (const e of log) {
    const p = e.payload as R, at = e.receivedAt;
    if (e.type === "paper") feed.push({ seq: e.seq, at, agent: "parser", text: `Extracted ${paper?.sentences?.length ?? 0} sentences · ${refs.length} references` });
    else if (e.type === "existence") { const [text, chip] = existenceText[String(p.status)] ?? ["Needs review", "NEEDS_REVIEW"]; feed.push({ seq: e.seq, at, agent: "resolver", text: `${refLabel(String(p.reference_id))} ${text}`, chip }); }
    else if (e.type === "retraction" && p.status !== "NONE") feed.push({ seq: e.seq, at, agent: "retraction", text: `${refLabel(String(p.reference_id))} ${p.status === "RETRACTED" ? `Retracted · ${p.reason}` : "Retraction status unknown"}`, chip: p.status === "RETRACTED" ? "RETRACTED" : "NEEDS_REVIEW" });
    else if (e.type === "support") feed.push({ seq: e.seq, at, agent: "verifier", text: `${citeLabel(String(p.citation_id))}`, chip: (["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED"].includes(String(p.label)) ? p.label : "NEEDS_REVIEW") as HeroChip });
    else if (e.type === "hidden_text") feed.push({ seq: e.seq, at, agent: "hidden", text: `Hidden text flagged on page ${p.page ?? "?"}` });
    else if (e.type === "review") feed.push({ seq: e.seq, at, agent: String(p.reviewer) as AgentId, text: `${agentDefs.find(d => d.id === p.reviewer)?.name ?? "Reviewer"} · ${String(p.severity).toLowerCase()} · ${clip(String(p.issue ?? ""), 70)}` });
    else if (e.type === "review_summary") feed.push({ seq: e.seq, at, agent: "chair", text: `Meta-review: ${(p.top_fixes as string[] | undefined)?.length ?? 0} priorities` });
    else if (e.type === "stage" && p.status === "CHECK_INCOMPLETE") { const owner = agentDefs.find(d => d.owns(String(p.stage))); feed.push({ seq: e.seq, at, agent: owner?.id ?? "parser", text: `${p.stage}: ${p.reason || "incomplete"}`, chip: "NEEDS_REVIEW" }); }
  }
  const slots: Slot[] = refs.map((r, i) => ({ id: r.id, index: i, label: `${r.authors?.[0] ?? "Reference"}${r.year ? ` ${r.year}` : ""}`, chip: existence.some(x => x.reference_id === r.id) ? referenceChip(report, r.id) : null }));
  const total = paper ? FIXED_STAGES + 3 * refs.length + citations.length : null, completed = finished.size;
  const first = log[0]?.receivedAt, d = done?.payload as { started_at?: string; finished_at?: string } | undefined;
  const recorded = d?.started_at && d?.finished_at ? (Date.parse(d.finished_at) - Date.parse(d.started_at)) / 1000 : NaN;
  const elapsed = done ? (Number.isFinite(recorded) ? recorded : (done.receivedAt - (first ?? done.receivedAt)) / 1000) : first ? (now - first) / 1000 : 0;
  const tally = (["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NOT_FOUND", "DOI_MISMATCH", "RETRACTED", "NEEDS_REVIEW"] as HeroChip[]).map(chip => ({ chip, count: slots.filter(s => s.chip === chip).length })).filter(t => t.count);
  return { title: paper?.title, agents, feed, slots, tally, progress: { completed, total }, elapsed, done: !!done };
}
export const formatElapsed = (s: number) => s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`;
