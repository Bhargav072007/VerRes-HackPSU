import type { components } from "./api-types";
import type { Report } from "./report";
import type { JobEvent } from "./job-stream";

export type ReviewComment = components["schemas"]["ReviewComment"];
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(s => typeof s === "string");
export function isReviewComment(v: unknown): v is ReviewComment {
  return object(v) && ["METHODS", "EVIDENCE", "CLAIMS"].includes(String(v.reviewer)) && ["MAJOR", "MINOR"].includes(String(v.severity))
    && strings(v.sentence_ids) && [v.quote, v.issue, v.suggestion].every(s => typeof s === "string") && (v.linked_citation_ids === undefined || strings(v.linked_citation_ids));
}
export function isReviewSummary(v: unknown): v is components["schemas"]["ReviewSummary"] {
  return object(v) && (v.top_fixes === undefined || strings(v.top_fixes)) && (v.comments === undefined || Array.isArray(v.comments) && v.comments.every(isReviewComment)) && (v.warning == null || typeof v.warning === "string");
}
export function readReview(v: Record<string, unknown>): Pick<Report, "review" | "review_comments" | "hidden_text" | "stages"> {
  const invalid = v.review != null && !isReviewSummary(v.review) || v.review_comments !== undefined && (!Array.isArray(v.review_comments) || !v.review_comments.every(isReviewComment));
  return {
    ...(invalid ? { review: { warning: "Review data could not be read. Needs review." }, review_comments: [] } : { review: v.review, review_comments: v.review_comments }),
    hidden_text: Array.isArray(v.hidden_text) ? v.hidden_text.filter(object) : [],
    stages: Array.isArray(v.stages) ? v.stages.filter(s => object(s) && typeof s.stage === "string" && ["STARTED", "COMPLETED", "CHECK_INCOMPLETE"].includes(String(s.status))) : [],
  } as Pick<Report, "review" | "review_comments" | "hidden_text" | "stages">;
}
export function applyReviewEvent(report: Report, event: JobEvent): Report {
  if (event.type === "review") return { ...report, review_comments: [...(report.review_comments ?? []), event.payload] };
  if (event.type === "review_summary") return { ...report, review: event.payload };
  if (event.type === "hidden_text") return { ...report, hidden_text: [...(report.hidden_text ?? []), event.payload] };
  if (event.type === "stage") return { ...report, stages: [...(report.stages ?? []).filter(s => s.stage !== event.payload.stage), event.payload] };
  return report;
}
export function reviewComments(report: Report): ReviewComment[] {
  return [...new Map([...(report.review_comments ?? []), ...(report.review?.comments ?? [])].map(c => [JSON.stringify(c), c])).values()];
}
export function hasReviewReceipt(report: Report, comment: ReviewComment): boolean {
  const normalize = (s: string) => s.replace(/\s+/g, " ").trim();
  const sentences = report.paper?.sentences ?? [];
  return !!normalize(comment.quote) && comment.sentence_ids.length > 0 && comment.sentence_ids.every(id => sentences.some(s => s.id === id))
    && normalize(sentences.filter(s => comment.sentence_ids.includes(s.id)).map(s => s.text).join(" ")).includes(normalize(comment.quote));
}
export function fixTarget(report: Report, fix: string): string | undefined {
  const comment = reviewComments(report).find(c => c.suggestion === fix && hasReviewReceipt(report, c));
  if (!comment) return;
  const citation = report.paper?.citations?.find(c => comment.linked_citation_ids?.includes(c.id) && c.sentence_ids?.some(id => comment.sentence_ids.includes(id)));
  return citation ? `citation-${citation.id}` : `sentence-${comment.sentence_ids[0]}`;
}
export function reviewState(report: Report) {
  const warning = report.review?.warning;
  const hiddenWarning = warning === "This paper contains hidden text addressed to AI reviewers.";
  const stages = report.stages?.filter(s => ["review_prep", "run_review_panel"].includes(s.stage)) ?? [];
  const failed = !!warning && !hiddenWarning || stages.some(s => s.status === "CHECK_INCOMPLETE");
  return { present: !!report.review || !!report.review_comments?.length || !!stages.length || ["RUNNING", "QUEUED"].includes(report.status),
    running: !failed && !report.review && ["RUNNING", "QUEUED"].includes(report.status),
    failed, hidden: hiddenWarning || !!report.hidden_text?.length };
}
