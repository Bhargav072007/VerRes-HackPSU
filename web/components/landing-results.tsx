import { landingReport as report } from "@/lib/landing-data";
import { MarginNote } from "./margin-note";
export function LandingResults() {
 const sentences = report.paper!.sentences!.filter(s => ["s00003", "s00005", "s00008"].includes(s.id));
 return <section className="article-section section-container" aria-labelledby="paper-view-title"><h2 id="paper-view-title" className="editorial-title">Read between <strong>the references.</strong></h2><figure className="paper-excerpt"><header><span>VerRes · Recorded manuscript</span><span>Paper 3 / excerpt</span></header>{sentences.map(s => {
  const c = report.paper!.citations!.find(c => c.sentence_ids?.includes(s.id))!;
  const missing = report.existence?.some(e => e.reference_id === c.reference_id && e.status === "NOT_FOUND");
  return <div className="excerpt-row" key={s.id}><p className="excerpt-text"><span className="line-number">{String(report.paper!.sentences!.indexOf(s)+1).padStart(2,"0")}</span>{missing ? <s className="pen-mark">{s.text}</s> : <span className={s.id === "s00005" ? "pen-mark" : undefined}>{s.text}</span>}</p><MarginNote report={report} citation={c} compact /></div>;
 })}<figcaption>Figure 1. Reviewer notes from a recorded VerRes run.</figcaption></figure></section>;
}
