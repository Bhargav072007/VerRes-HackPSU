import { citationVerdict, verifiedEvidence, type Citation, type Report } from "./report";

export const getFlag = () => new URLSearchParams(window.location.search).get("flag") || "";
export function subscribeFlag(change: () => void) {
  window.addEventListener("popstate", change);
  return () => window.removeEventListener("popstate", change);
}
export function updateFlag(id: string) {
  const url = new URL(window.location.href);
  if (getFlag() === id) return;
  if (id) url.searchParams.set("flag", id); else url.searchParams.delete("flag");
  window.history.pushState(null, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function evidenceDetails(report: Report, citation: Citation) {
  const support = report.support?.find(s => s.citation_id === citation.id);
  const source = report.sources?.find(s => s.reference_id === citation.reference_id);
  const existence = report.existence?.find(s => s.reference_id === citation.reference_id);
  const retraction = report.retractions?.find(s => s.reference_id === citation.reference_id);
  const verdict = citationVerdict(report, citation), quotes = verifiedEvidence(report, citation);
  const incomplete = !support?.evidence?.length || quotes.length !== support.evidence.length;
  const reason = verdict === "RETRACTED" ? retraction?.reason : verdict === "DOI_MISMATCH" || verdict === "NOT_FOUND" ? existence?.reason : support?.reason;
  const pendingCheck = existence?.status !== "VERIFIED" ? existence?.reason || "Citation existence check incomplete."
    : retraction?.status !== "NONE" ? retraction?.reason || "Retraction check incomplete." : null;
  const needsReview = verdict !== "NEEDS_REVIEW" ? null
    : pendingCheck || support?.needs_review_reason || (source?.status !== "AVAILABLE" ? source?.reason : null)
      || (source?.evidence_level === "ABSTRACT_ONLY" ? "Abstract only: full text needed" : null)
      || (support?.label === "NEEDS_REVIEW" ? support.reason : null)
      || (incomplete ? "Verified source quotes are missing or could not be matched. Inspect the source." : null)
      || support?.reason || "Claim support check incomplete. Inspect the available receipts.";
  const urls = [...(existence?.receipt_urls ?? []), ...(retraction?.notice_urls ?? [])];
  const doi = report.paper?.references?.find(r => r.id === citation.reference_id)?.doi;
  if (doi) urls.unshift(`https://doi.org/${doi}`);
  const links = Array.from(new Set(urls)).flatMap(href => {
    try {
      const url = new URL(href);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return [];
      const label = /^(dx\.)?doi\.org$/.test(url.hostname) ? "DOI" : /^(api\.)?openalex\.org$/.test(url.hostname) ? "OpenAlex" : retraction?.notice_urls?.includes(href) ? "Retraction notice" : "Open-access copy / receipt";
      return [{ href, label }];
    } catch { return []; }
  });
  const agreement = support?.adjudicated === true && ["NOT_SUPPORTED", "CONTRADICTED"].includes(verdict) ? "2 of 2 models agree"
    : verdict === "NEEDS_REVIEW" && /models disagree/i.test(`${support?.needs_review_reason} ${support?.reason}`) ? "Models disagree" : null;
  return { verdict, quotes, source, support, reason, needsReview, links, agreement, mismatches: [...(support?.mismatch_types ?? []), ...(existence?.discrepancies ?? [])] };
}
