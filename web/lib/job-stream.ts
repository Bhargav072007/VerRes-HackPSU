import type { components } from "./api-types";
import { isReviewComment, isReviewSummary } from "./review";

type Schema = components["schemas"];
export type JobEvent = Schema["SSEEvent"] & { payload: { provenance?: { cached_at: string } } };
export const eventTypes = ["stage", "paper", "existence", "retraction", "source", "support", "claim_map", "hidden_text", "review", "review_summary", "done", "error"] as const;
export const stages = ["parse", "references", "existence", "retraction", "support", "review", "report"];
export type Row = { reference: Schema["Reference"]; existence?: Schema["ExistenceResult"]; retraction?: Schema["RetractionResult"]; cachedAt?: string };
export type JobState = {
  seq: number; rows: Record<string, Row>; paper?: Schema["Paper"]; support: Record<string, Schema["SupportResult"]>;
  stages: Record<string, Schema["StagePayload"]["status"]>; errors: Record<string, string>; done: boolean;
};
export const initialJob: JobState = { seq: 0, rows: {}, support: {}, stages: {}, errors: {}, done: false };
type Action = { type: "reset" } | { type: "event"; event: JobEvent } | { type: "snapshot"; events: unknown[] } | { type: "notice"; reason: string };
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const string = (value: unknown): value is string => typeof value === "string";

// Validate the fields this view consumes. Unrecognized external data stays incomplete.
export function decodeEvent(value: unknown): JobEvent | null {
  if (!object(value) || !Number.isSafeInteger(value.seq) || Number(value.seq) < 1 || !string(value.type) || !object(value.payload)) return null;
  const p = value.payload;
  if (["receipt_urls", "notice_urls"].some(key => p[key] != null && (!Array.isArray(p[key]) || !p[key].every(string)))) return null;
  const paper = (v: unknown) => object(v) && (v.title == null || string(v.title)) && Array.isArray(v.references) && v.references.every(r => object(r) && string(r.id) && string(r.raw_text) && (r.title == null || string(r.title))) && Array.isArray(v.citations) && v.citations.every(c => object(c) && string(c.id) && string(c.reference_id));
  const valid = value.type === "paper" ? paper(p)
    : value.type === "stage" ? string(p.stage) && ["STARTED", "COMPLETED", "CHECK_INCOMPLETE"].includes(String(p.status))
    : value.type === "existence" ? string(p.reference_id) && string(p.reason) && ["VERIFIED", "VERIFIED_WITH_DISCREPANCIES", "DOI_MISMATCH", "AMBIGUOUS", "NOT_FOUND", "UNCHECKABLE", "CHECK_INCOMPLETE"].includes(String(p.status))
    : value.type === "retraction" ? string(p.reference_id) && string(p.reason) && ["NONE", "RETRACTED", "EXPRESSION_OF_CONCERN", "CORRECTED", "UNKNOWN"].includes(String(p.status))
    : value.type === "support" ? string(p.citation_id) && string(p.reason) && ["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NEEDS_REVIEW"].includes(String(p.label)) && (p.label === "NEEDS_REVIEW" || (Array.isArray(p.evidence) && p.evidence.length > 0 && p.evidence.every(e => object(e) && string(e.quote) && string(e.passage_id))))
    : value.type === "review" ? isReviewComment(p)
    : value.type === "review_summary" ? isReviewSummary(p)
    : value.type === "error" ? string(p.reason)
    : value.type === "done" ? ["COMPLETE", "NEEDS_REVIEW", "CHECK_INCOMPLETE"].includes(String(p.status))
    : eventTypes.includes(value.type as typeof eventTypes[number]);
  return valid ? value as unknown as JobEvent : null;
}

export function jobReducer(state: JobState, action: Action): JobState {
  if (action.type === "reset") return initialJob;
  if (action.type === "notice") return { ...state, errors: { ...state.errors, connection: action.reason } };
  if (action.type === "snapshot") return action.events.reduce<JobState>((s, e) => {
    const event = decodeEvent(e);
    return event ? jobReducer(s, { type: "event", event }) : jobReducer(s, { type: "notice", reason: "CHECK_INCOMPLETE: unreadable event; review continues." });
  }, state);
  const e = action.event;
  if (e.seq <= state.seq) return state;
  const next = { ...state, seq: e.seq };
  if (e.type === "paper") {
    next.paper = e.payload;
    next.stages = { ...state.stages, parse: "COMPLETED", references: "COMPLETED", existence: state.stages.existence ?? "STARTED" };
    next.rows = { ...state.rows };
    for (const reference of e.payload.references ?? []) next.rows[reference.id] = { ...next.rows[reference.id], reference };
  } else if (e.type === "existence" || e.type === "retraction") {
    next.stages = { ...state.stages, [e.type]: state.stages[e.type] ?? "STARTED" };
    const id = e.payload.reference_id;
    const cachedAt = e.payload.provenance?.cached_at;
    next.rows = { ...state.rows, [id]: { ...state.rows[id], [e.type]: e.payload, cachedAt: typeof cachedAt === "string" && Number.isFinite(Date.parse(cachedAt)) ? cachedAt : undefined } };
  } else if (e.type === "support") {
    next.support = { ...state.support, [e.payload.citation_id]: e.payload };
    next.stages = { ...state.stages, support: state.stages.support ?? "STARTED" };
  } else if (e.type === "stage") {
    next.stages = { ...state.stages, [e.payload.stage === "paper" ? "parse" : e.payload.stage]: e.payload.status };
    if (e.payload.status === "CHECK_INCOMPLETE") next.errors = { ...state.errors, [e.seq]: e.payload.reason || "Stage incomplete. Needs review." };
  }
  else if (e.type === "error") next.errors = { ...state.errors, [e.seq]: e.payload.reason };
  else if (e.type === "done") {
    next.done = true;
    next.stages = { ...state.stages, report: "COMPLETED" };
    next.errors = { ...state.errors };
    delete next.errors.connection;
    if (typeof e.payload.reason === "string") next.errors.final = e.payload.reason;
  }
  return next;
}

export function jobCounts(state: JobState) {
  const refs = Object.values(state.rows), support = Object.values(state.support);
  const uncertain = new Set(refs.filter(r => r.existence && !["VERIFIED", "NOT_FOUND"].includes(r.existence.status) || r.retraction && !["NONE", "RETRACTED"].includes(r.retraction.status)).map(r => r.reference?.id));
  for (const s of support.filter(s => s.label === "NEEDS_REVIEW")) uncertain.add(state.paper?.citations?.find(c => c.id === s.citation_id)?.reference_id ?? s.citation_id);
  return { checked: (state.paper?.citations ?? []).filter(c => state.rows[c.reference_id]?.existence).length, total: state.paper?.citations?.length ?? 0, missing: refs.filter(r => r.existence?.status === "NOT_FOUND").length, retracted: refs.filter(r => r.retraction?.status === "RETRACTED").length, overstated: support.filter(s => s.label === "PARTIALLY_SUPPORTED").length, needsReview: uncertain.size };
}

// The journal names individual source checks; present those as readable phases.
export function stageStatus(state: JobState, stage: string) {
  const aliases: Record<string, string[]> = { parse: ["parse_pdf"], existence: ["existence:"], retraction: ["retraction:"], support: ["source:", "support:"], review: ["run_review_panel"], report: ["summary"] };
  const tasks = Object.entries(state.stages).filter(([key]) => aliases[stage]?.some(alias => alias.endsWith(":") ? key.startsWith(alias) : key === alias)).map(([, status]) => status);
  if (!tasks.length) return state.stages[stage];
  return tasks.includes("STARTED") ? "STARTED" : tasks.includes("CHECK_INCOMPLETE") ? "CHECK_INCOMPLETE" : "COMPLETED";
}
