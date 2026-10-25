import Link from "next/link";
import { landingReport as report } from "@/lib/landing-data";
import { MarginNote } from "./margin-note";
import { MockupImage } from "./mockup-image";
export function LandingScene() {
 const bert = report.paper!.citations!.find(c => c.id === "c00003")!;
 const missing = report.paper!.references!.find(r => report.existence?.some(e => e.reference_id === r.id && e.status === "NOT_FOUND"));
 return <section className="hero section-container" aria-labelledby="headline"><h1 id="headline" data-reveal>Read your paper like<br className="desktop-break" /> Reviewer 2 would.</h1><p className="hero-lead">VerRes checks every reference in your manuscript, finds the passage you cited, and flags where a claim goes further than its source — before anyone else does.</p><div className="hero-actions"><a className="pill-button" href="#submit">Review a paper</a><Link className="outline-button" href="/report/sample-paper3">See a sample report</Link></div><p className="hero-caption">Every finding links to its evidence.</p><div className="hero-photo"><MockupImage scene="s1" priority sizes="(max-width: 1248px) 100vw, 1200px" alt="A recorded VerRes paper review on a library laptop" /><div className="hero-details"><MarginNote report={report} citation={bert} compact />{missing && <aside className="reference-detail"><span className="source-identifier">Reference {report.paper!.references!.indexOf(missing)+1}</span><p><s>{missing.title}</s></p><p>Not found in Crossref, OpenAlex or arXiv</p></aside>}</div></div></section>;
}
