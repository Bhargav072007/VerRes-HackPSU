import type { components } from "./api-types";

type Support = components["schemas"]["SupportResult"];
type Source = components["schemas"]["SourceDocument"];
export type ReviewOutcome = "BACKGROUND_CITATION" | "METHOD_REFERENCE" | "INFORMATIONAL_CITATION" | "CHECK_INCOMPLETE" | "SECOND_CHECK_PENDING" | "INSUFFICIENT_EVIDENCE";
export const informationalOutcomes: readonly string[] = ["BACKGROUND_CITATION", "METHOD_REFERENCE", "INFORMATIONAL_CITATION"];

// Presentation categories preserve the API's conservative NEEDS_REVIEW verdict.
export function reviewOutcome(support?: Pick<Support, "reason" | "needs_review_reason">): ReviewOutcome {
  const reason = support?.needs_review_reason || support?.reason || "";
  if (reason === "Background citation: no specific factual finding is attributed to this source.") return "BACKGROUND_CITATION";
  if (reason === "Method reference: this citation identifies a method or tool, not a specific finding.") return "METHOD_REFERENCE";
  if (reason === "citation does not attribute a specific finding") return "INFORMATIONAL_CITATION";
  if (/eligible adjudicator|requires independent adjudication/i.test(reason)) return "SECOND_CHECK_PENDING";
  if (/abstract does not address|abstract evidence|extracted text cannot|models disagree|quote or passage|indirect evidence|attribution.*ambiguous/i.test(reason)) return "INSUFFICIENT_EVIDENCE";
  if (!support || /model call failed|output failed schema|classification failed|failed \([A-Z]|not configured|Source unavailable:|source evidence is unavailable|check incomplete|timed out|budget|HTTP_|circuit open|identity is not verified/i.test(reason)) return "CHECK_INCOMPLETE";
  return "INSUFFICIENT_EVIDENCE";
}

export function sourceEvidenceLabel(source?: Pick<Source, "reason" | "evidence_level"> | null) {
  if (source?.reason?.startsWith("Partial PDF text coverage:")) return "Extracted PDF text · partial coverage";
  return source?.evidence_level === "FULL_TEXT" ? "Full text" : source?.evidence_level === "ABSTRACT_ONLY" ? "Abstract only" : "Metadata only";
}
