import { NoteTint } from "./editorial-motion";
import { citationDisplayVerdict, verifiedEvidence, type Citation, type Report } from "@/lib/report";
import { VerdictBadge } from "./verdict-badge";
export function MarginNote({ report, citation, compact = false }: { report: Report; citation: Citation; compact?: boolean }) {
  const evidence = verifiedEvidence(report, citation)[0];
  const reference = report.paper?.references?.find(r => r.id === citation.reference_id);
  const identifier = reference?.doi ? `DOI ${reference.doi}` : reference?.arxiv_id ? `arXiv:${reference.arxiv_id}` : "Source identity unverified";
  return <div className="margin-note" role="note" aria-label="Reviewer note"><NoteTint /><VerdictBadge status={citationDisplayVerdict(report, citation)} />{evidence ? <blockquote>{compact ? evidence.quote.split(" ").slice(0, 32).join(" ") + (evidence.quote.split(" ").length > 32 ? "…" : "") : evidence.quote}</blockquote> : <p>{report.support?.find(s => s.citation_id === citation.id)?.reason || "This check has no verified source quote."}</p>}<p className="source-identifier">{identifier}</p></div>;
}
