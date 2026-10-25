import { readFileSync } from "node:fs";
import { replayReport, type Verdict } from "../../lib/report";

export const evidenceStates: Verdict[] = ["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NEEDS_REVIEW", "DOI_MISMATCH", "RETRACTED", "NOT_FOUND"];
export function evidenceFixture() {
  const base = replayReport(readFileSync("public/fixtures/events/paper1.jsonl", "utf8").trim().split("\n").map(line => JSON.parse(line)))!;
  const paper = base.paper!;
  const claims = evidenceStates.map((_, i) => i === 0 ? "treatment improved outcomes in adults" : "treatment benefits extend to children");
  const quotes = evidenceStates.map((_, i) => i === 0 ? "Treatment improved outcomes in adults." : "children were not enrolled.");
  return { ...base, paper: { ...paper, title: "Evidence receipts: a fixture study", sentences: evidenceStates.map((_, i) => ({ ...paper.sentences![0], id: `s-${i}`, text: `In this study, ${claims[i]}.` })), references: evidenceStates.map((_, i) => ({ ...paper.references![0], id: `r-${i}`, doi: "10.1234/fixture" })), citations: evidenceStates.map((_, i) => ({ ...paper.citations![0], id: `c-${i}`, reference_id: `r-${i}`, sentence_ids: [`s-${i}`], claim_text: claims[i] })) },
    existence: evidenceStates.map((state, i) => ({ ...base.existence![0], reference_id: `r-${i}`, status: state === "DOI_MISMATCH" || state === "NOT_FOUND" ? state : "VERIFIED" as const, reason: state === "DOI_MISMATCH" ? "The DOI resolves to a different study." : "Fixture metadata matched.", receipt_urls: ["https://doi.org/10.1234/fixture", "https://openalex.org/W123", "https://example.org/open-access.pdf", "javascript:alert(1)"] })),
    retractions: evidenceStates.map((state, i) => ({ ...base.retractions![0], reference_id: `r-${i}`, status: state === "RETRACTED" ? "RETRACTED" as const : "NONE" as const, reason: "The publisher issued a retraction notice.", notice_urls: state === "RETRACTED" ? ["https://example.org/retraction"] : [] })),
    sources: evidenceStates.map((_, i) => ({ ...base.sources![1], reference_id: `r-${i}`, passages: [{ passage_id: "p1", text: quotes[i], section: null, page: 1 }], evidence_level: i === 4 ? "ABSTRACT_ONLY" as const : "FULL_TEXT" as const })),
    support: evidenceStates.map((state, i) => ({ ...base.support![2], citation_id: `c-${i}`, label: ["DOI_MISMATCH", "RETRACTED", "NOT_FOUND"].includes(state) ? "NEEDS_REVIEW" as const : state as NonNullable<typeof base.support>[number]["label"], evidence: [{ passage_id: "p1", quote: quotes[i] }], mismatch_types: i === 0 ? [] : ["POPULATION" as const], reason: i === 0 ? "The source reports improved outcomes in adults." : "The adult cohort does not establish benefits for children.", needs_review_reason: state === "NEEDS_REVIEW" ? "Abstract only: full text needed" : null, adjudicated: state === "NOT_SUPPORTED" || state === "CONTRADICTED" })) };
}
