import demo from "@/fixtures/demo/paper3.json";
import paper2 from "@/tests/fixtures/prod/paper2-job.json";
import paper3 from "@/tests/fixtures/prod/paper3-job.json";
import { citationSupportVerdict, decodeReport, referenceVerdict, verifiedEvidence, type Report } from "./report";
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

// "How it works" demo cards, each built from a recorded run.
const [run2, run3] = recordings.map(r => decodeReport(r)!);
const byline = (r: { authors?: string[] | null; year?: number | null }) => `${r.authors?.[0] ?? "Unknown author"}${(r.authors?.length ?? 0) > 1 ? " et al." : ""} ${r.year ?? "n.d."}`;
const existenceLabels: Record<string, [string, string]> = { VERIFIED: ["FOUND", "sage"], NOT_FOUND: ["NOT FOUND", "red"], DOI_MISMATCH: ["DOI MISMATCH", "red"] };
const bert = landingReport.paper!.citations!.find(c => c.id === "c00003")!;
const reviewers = [["METHODS", "Methods"], ["CLAIMS", "Claims"], ["EVIDENCE", "Evidence"]] as const;
export const stepperDemo = {
  parse: run3.paper!.sentences!.slice(2, 6).map((s, i) => ({ line: i + 3, text: s.text })),
  resolve: run3.paper!.references!.map(r => { const status = run3.existence?.find(e => e.reference_id === r.id)?.status ?? ""; const [label, tone] = existenceLabels[status] ?? ["NEEDS REVIEW", "blue"]; return { id: r.id, byline: byline(r), title: r.title ?? "Untitled reference", label, tone }; }),
  retraction: run2.paper!.references!.map(r => {
    const check = run2.retractions?.find(x => x.reference_id === r.id);
    const retracted = check?.status === "RETRACTED";
    const notice = retracted ? (check.source_url && check.notice_urls?.includes(check.source_url) ? check.source_url : check.notice_urls?.[0]) : undefined;
    return { id: r.id, byline: byline(r), title: r.title ?? "Untitled reference", retracted, year: retracted ? check.reason?.match(/retraction date: (\d{4})/)?.[1] ?? null : null, notice };
  }),
  source: { identifier: `arXiv:${landingReport.paper!.references!.find(r => r.id === bert.reference_id)?.arxiv_id}`, level: "Abstract", passage: verifiedEvidence(landingReport, bert)[0]?.quote ?? null },
  verify: { claim: landingReport.paper!.sentences!.find(s => bert.sentence_ids?.includes(s.id))!.text, quote: verifiedEvidence(landingReport, bert)[0]?.quote ?? null, verdict: citationSupportVerdict(landingReport, bert) },
  review: {
    panel: reviewers.map(([key, name], i) => { const comments = run3.review?.comments?.filter(c => c.reviewer === key) ?? []; return { id: `R${i + 1}`, name, major: comments.filter(c => c.severity === "MAJOR").length, minor: comments.filter(c => c.severity === "MINOR").length }; }),
    areaChair: run3.review?.top_fixes?.find(f => /BERT/.test(f)) ?? run3.review?.top_fixes?.[0] ?? null,
  },
};
