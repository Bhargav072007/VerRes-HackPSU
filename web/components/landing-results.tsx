"use client";
import demo from "@/fixtures/demo/paper3.json";
import { citationSupportVerdict, decodeReport, referenceVerdict, verifiedEvidence } from "@/lib/report";
import { VerdictBadge } from "./verdict-badge";
const report = decodeReport(demo);
export function LandingResults() {
  return <section id="results" className="article-section section-container" data-section="3 · RESULTS"><div className="article-section-title" data-enter><span>3</span><h2>Results</h2></div><p className="section-intro">A recorded review of a manuscript with planted problems. These are the recorded findings, with source passages checked verbatim.</p><div className="results-preview">{report?.paper?.citations?.filter(c => ["c00001", "c00002", "c00005"].includes(c.id)).map(c => { const quote = verifiedEvidence(report, c)[0]; return <article key={c.id} data-enter><div className="result-heading"><span>Claim {c.id.replace("c0000", "")}</span><VerdictBadge status={citationSupportVerdict(report, c)} /></div><h3>{c.claim_text}</h3>{quote ? <blockquote>“{quote.quote}”</blockquote> : <p>No verified source quote is available. <VerdictBadge status="NEEDS_REVIEW" /></p>}<div className="result-source"><span>{report.paper?.references?.find(r => r.id === c.reference_id)?.title}</span><VerdictBadge status={referenceVerdict(report, c.reference_id)} /></div></article>; })}</div><p className="figure-caption">Recorded demo · paper3 · Source availability and claim support are separate findings.</p></section>;
}
