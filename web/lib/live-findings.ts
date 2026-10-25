import type { JobState } from "./job-stream";
import { claimGraph } from "./claim-graph";
import { citationVerdict, referenceVerdict, verifiedEvidence, type Report, type Verdict } from "./report";

export function liveFindings(state: JobState) {
  const report = { status: "RUNNING", paper: state.paper, existence: Object.values(state.rows).flatMap(r => r.existence ? [r.existence] : []), retractions: Object.values(state.rows).flatMap(r => r.retraction ? [r.retraction] : []), sources: Object.values(state.sources), support: Object.values(state.support), claim_map: state.claimMap } as Report;
  const citations = state.paper?.citations ?? [], references = state.paper?.references ?? [];
  const findings: { id: string; seq: number; sentence: string; verdict: Verdict; citationId?: string; hiddenId?: string }[] = [];
  for (const r of references) {
    const row = state.rows[r.id], name = `Reference [${references.indexOf(r) + 1}]`;
    for (const type of ["existence", "retraction"] as const) {
      const status = row?.[type]?.status;
      if (status !== "RETRACTED" && status !== "NOT_FOUND" && status !== "DOI_MISMATCH") continue;
      const id = `${type}:${r.id}`;
      findings.push({ id, seq: state.received[id], verdict: status, citationId: citations.find(c => c.reference_id === r.id)?.id,
        sentence: status === "RETRACTED" ? `${name} has been retracted.` : status === "NOT_FOUND" ? `${name} was not found in Crossref, OpenAlex or arXiv.` : `${name} has a DOI that points to a different work.` });
    }
  }
  for (const c of citations) {
    if (state.support[c.id]?.label !== "CONTRADICTED") continue;
    const complete = citationVerdict(report, c) === "CONTRADICTED";
    findings.push({ id: `support:${c.id}`, seq: state.received[`support:${c.id}`], citationId: c.id, verdict: complete ? "CONTRADICTED" : "NEEDS_REVIEW", sentence: complete ? `A claim citing reference [${references.findIndex(r => r.id === c.reference_id) + 1}] is contradicted by its source.` : "A claim check needs review because its source or quote could not be verified." });
  }
  for (const h of Object.values(state.hidden)) findings.push({ id: `hidden_text:${h.id}`, seq: state.received[`hidden_text:${h.id}`], hiddenId: `${h.page ?? null}-${Object.values(state.hidden).filter(item => item.page === h.page).findIndex(item => item.id === h.id)}`, verdict: "NEEDS_REVIEW", sentence: h.kind === "CHECK_INCOMPLETE" ? "The hidden-text scan could not be completed and needs review." : `Hidden text${h.page ? ` on page ${h.page}` : ""} needs review.` });
  findings.sort((a, b) => b.seq - a.seq);
  return { report, findings, quotes: citations.reduce((n, c) => n + verifiedEvidence(report, c).length, 0),
    dots: references.map(r => ({ id: r.id, checked: !!state.rows[r.id]?.existence, verdict: referenceVerdict(report, r.id) })) };
}

export function liveGraph(state: JobState, report: Report) {
  // Parsed citation claims are real paper text; relationships wait for claim_map.
  const blank = { source_url: null, source_type: null, retrieved_at: null, evidence_level: null, quote_offsets: null, model_id: null, prompt_version: null };
  const claim_map = state.claimMap ?? { ...blank, paper_id: state.paper?.id ?? "", status: "NEEDS_REVIEW" as const, needs_review_reason: null, edges: [], nodes: (state.paper?.citations ?? []).filter(c => c.claim_text?.trim()).map(c => ({ ...blank, id: c.id, text: c.claim_text, sentence_ids: c.sentence_ids ?? [], citation_ids: [c.id], kind: "CLAIM" as const })) };
  return claimGraph({ ...report, claim_map });
}
