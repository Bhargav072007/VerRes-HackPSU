import demo from "@/fixtures/demo/paper3.json";
import paper2 from "@/tests/fixtures/prod/paper2-job.json";
import paper3 from "@/tests/fixtures/prod/paper3-job.json";
import { citationSupportVerdict, decodeReport, referenceVerdict, type Report } from "./report";
export const landingReport = decodeReport(demo)!;
const recordings = [paper2, paper3];
const runtimes = recordings.map(r => (Date.parse(r.finished_at) - Date.parse(r.started_at)) / 1000).filter(Number.isFinite).sort((a,b) => a-b);
export const recordedStats = {
  manuscripts: recordings.length,
  medianSeconds: runtimes.length ? Math.round((runtimes[Math.floor((runtimes.length-1)/2)] + runtimes[Math.floor(runtimes.length/2)]) / 2) : null,
};

export const productChecks = ["Existence", "DOI match", "Retraction", "Claim support", "Hidden text", "Peer-review panel"] as const;
export const scholarlySources = ["Crossref", "OpenAlex", "arXiv", "PubMed", "Retraction Watch"] as const;

// Hero scene: every reference from the two recorded manuscripts becomes one verdict chip.
export type HeroChip = "SUPPORTED" | "PARTIALLY_SUPPORTED" | "NOT_SUPPORTED" | "CONTRADICTED" | "NOT_FOUND" | "DOI_MISMATCH" | "RETRACTED" | "NEEDS_REVIEW";
export const heroChipLabels: Record<HeroChip, [glyph: string, label: string, tone: string]> = {
  SUPPORTED: ["✓", "Supported", "sage"], PARTIALLY_SUPPORTED: ["◐", "Partial", "brass"], NOT_SUPPORTED: ["✕", "Not supported", "red"], CONTRADICTED: ["✕", "Contradicted", "red"],
  NOT_FOUND: ["✕", "Not found", "red"], DOI_MISMATCH: ["✕", "DOI mismatch", "red"], RETRACTED: ["✕", "Retracted", "red"], NEEDS_REVIEW: ["?", "Needs review", "blue"],
};
export function referenceChip(report: Report, id: string): HeroChip {
  const verdict = referenceVerdict(report, id);
  if (verdict !== "SUPPORTED") return verdict as HeroChip;
  const support = (report.paper?.citations ?? []).filter(c => c.reference_id === id).map(c => citationSupportVerdict(report, c));
  return support.find(v => v === "CONTRADICTED" || v === "NOT_SUPPORTED" || v === "PARTIALLY_SUPPORTED") ?? (support.includes("SUPPORTED") ? "SUPPORTED" : "NEEDS_REVIEW");
}
export const heroCards = recordings.flatMap(recording => {
  const report = decodeReport(recording);
  return (report?.paper?.references ?? []).map(r => ({ id: `${recording.job_id}-${r.id}`, author: r.authors?.[0] ? `${r.authors[0]}${r.authors.length > 1 ? " et al." : ""}` : "Unknown author", year: r.year ?? null, title: r.title || "Untitled reference", chip: referenceChip(report!, r.id) }));
});
const countWords = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"];
export const countWord = (n: number) => countWords[n] ?? String(n);
