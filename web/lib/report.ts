import type { components, paths } from "./api-types";
import { readReview } from "./review";

type Snapshot = paths["/jobs/{job_id}"]["get"]["responses"][200]["content"]["application/json"];
export type Report = Pick<Snapshot, "paper" | "existence" | "retractions" | "sources" | "support" | "claim_map" | "status" | "reason" | "review" | "review_comments" | "hidden_text" | "stages">;
export type Citation = components["schemas"]["Citation"];
export type Filter = "All" | "Problems only" | "Needs review";
export type Verdict = components["schemas"]["SupportLabel"] | "NOT_FOUND" | "DOI_MISMATCH" | "RETRACTED";
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown) => v == null || typeof v === "string";
const list = (v: unknown, check: (item: Record<string, unknown>) => boolean) => v === undefined || Array.isArray(v) && v.every(item => object(item) && check(item));
const strings = (v: unknown) => v === undefined || Array.isArray(v) && v.every(item => typeof item === "string");

// Validate every field the reader consumes; malformed external data stays incomplete.
export function decodeReport(value: unknown): Report | null {
  if (!object(value) || !["QUEUED", "RUNNING", "COMPLETE", "NEEDS_REVIEW", "CHECK_INCOMPLETE"].includes(String(value.status)) || !text(value.reason)) return null;
  const p = value.paper;
  const map = value.claim_map;
  if (map != null && (!object(map) || typeof map.paper_id !== "string" || typeof map.status !== "string" || !["COMPLETE", "NEEDS_REVIEW"].includes(map.status) || !text(map.needs_review_reason)
    || !list(map.nodes, n => typeof n.id === "string" && typeof n.text === "string" && strings(n.sentence_ids) && strings(n.citation_ids) && typeof n.kind === "string" && ["CLAIM", "EVIDENCE", "ASSUMPTION"].includes(n.kind))
    || !list(map.edges, e => typeof e.source_id === "string" && typeof e.target_id === "string" && typeof e.reason === "string" && typeof e.relation === "string" && ["SUPPORTS", "CONTRADICTS", "DEPENDS_ON"].includes(e.relation) && list(e.evidence, q => typeof q.passage_id === "string" && typeof q.quote === "string")))) return null;
  if (p != null && (!object(p) || !text(p.title) || !text(p.needs_review_reason) || !strings(p.authors)
    || !list(p.sentences, s => typeof s.id === "string" && typeof s.text === "string" && text(s.section))
    || !list(p.references, r => typeof r.id === "string" && typeof r.raw_text === "string" && text(r.title) && text(r.doi) && (r.year == null || Number.isInteger(r.year)))
    || !list(p.citations, c => typeof c.id === "string" && typeof c.reference_id === "string" && strings(c.sentence_ids) && text(c.claim_text)))) return null;
  if (!list(value.existence, e => typeof e.reference_id === "string" && typeof e.status === "string" && text(e.reason) && strings(e.receipt_urls) && strings(e.discrepancies))
    || !list(value.retractions, r => typeof r.reference_id === "string" && typeof r.status === "string" && text(r.reason) && strings(r.notice_urls))
    || !list(value.sources, s => typeof s.reference_id === "string" && ["FULL_TEXT", "ABSTRACT_ONLY", "METADATA_ONLY"].includes(String(s.evidence_level)) && text(s.reason) && list(s.passages, p => typeof p.passage_id === "string" && typeof p.text === "string"))
    || !list(value.support, s => typeof s.citation_id === "string" && typeof s.label === "string" && text(s.reason) && text(s.needs_review_reason) && strings(s.mismatch_types) && (s.adjudicated === undefined || typeof s.adjudicated === "boolean") && list(s.evidence, e => typeof e.passage_id === "string" && typeof e.quote === "string"))) return null;
  return { ...value, ...readReview(value) } as Report;
}

export function replayReport(events: unknown[]): Report | null {
  const done = events.findLast(e => object(e) && e.type === "done");
  return object(done) ? decodeReport(done.payload) : null;
}

export async function loadReport(id: string, signal: AbortSignal): Promise<Report | null> {
  try {
    const mock = process.env.NEXT_PUBLIC_MOCK === "1";
    const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
    const response = await fetch(mock ? "/fixtures/events/paper1.jsonl" : `${base}/jobs/${encodeURIComponent(id)}`, { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]) });
    if (!response.ok) return null;
    return mock ? replayReport((await response.text()).trim().split("\n").map(line => JSON.parse(line))) : decodeReport(await response.json());
  } catch { return null; }
}

export function referenceVerdict(report: Report, id: string): Verdict {
  const existence = report.existence?.find(e => e.reference_id === id)?.status;
  const retraction = report.retractions?.find(r => r.reference_id === id)?.status;
  if (retraction === "RETRACTED") return "RETRACTED";
  if (existence === "NOT_FOUND" || existence === "DOI_MISMATCH") return existence;
  return existence === "VERIFIED" ? "SUPPORTED" : "NEEDS_REVIEW";
}

export function verifiedEvidence(report: Report, citation: Citation) {
  const source = report.sources?.find(s => s.reference_id === citation.reference_id);
  const support = report.support?.find(s => s.citation_id === citation.id);
  if (source?.status !== "AVAILABLE") return [];
  return (support?.evidence ?? []).filter(e => e.quote.trim() && source.passages?.some(p => p.passage_id === e.passage_id && p.text.includes(e.quote)));
}

export function citationVerdict(report: Report, citation: Citation): Verdict {
  if (report.retractions?.some(r => r.reference_id === citation.reference_id && r.status === "RETRACTED")) return "RETRACTED";
  return citationSupportVerdict(report, citation);
}

export function citationSupportVerdict(report: Report, citation: Citation): components["schemas"]["SupportLabel"] {
  const support = report.support?.find(s => s.citation_id === citation.id);
  return support && ["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED"].includes(support.label)
    && !!support.evidence?.length && verifiedEvidence(report, citation).length === support.evidence.length ? support.label : "NEEDS_REVIEW";
}

export function matchesFilter(verdicts: Verdict[], filter: Filter) {
  return filter === "All" || verdicts.some(v => filter === "Needs review" ? v === "NEEDS_REVIEW" : v !== "SUPPORTED");
}

export function reportCounts(report: Report) {
  const refs = report.paper?.references ?? [], citations = report.paper?.citations ?? [];
  return [refs.length, report.existence?.filter(e => e.status === "NOT_FOUND").length ?? 0,
    report.existence?.filter(e => e.status === "DOI_MISMATCH").length ?? 0,
    report.retractions?.filter(r => r.status === "RETRACTED").length ?? 0,
    citations.filter(c => citationVerdict(report, c) === "PARTIALLY_SUPPORTED").length,
    refs.filter(r => referenceVerdict(report, r.id) === "NEEDS_REVIEW" || citations.some(c => c.reference_id === r.id && citationVerdict(report, c) === "NEEDS_REVIEW")).length];
}
