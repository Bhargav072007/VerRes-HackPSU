import demo from "@/fixtures/demo/paper3.json";
import paper2 from "@/tests/fixtures/prod/paper2-job.json";
import paper3 from "@/tests/fixtures/prod/paper3-job.json";
import { decodeReport } from "./report";
export const landingReport = decodeReport(demo)!;
const recordings = [paper2, paper3];
const runtimes = recordings.map(r => (Date.parse(r.finished_at) - Date.parse(r.started_at)) / 1000).filter(Number.isFinite).sort((a,b) => a-b);
export const recordedStats = {
  manuscripts: recordings.length,
  medianSeconds: runtimes.length ? Math.round((runtimes[Math.floor((runtimes.length-1)/2)] + runtimes[Math.floor(runtimes.length/2)]) / 2) : null,
};

export const productChecks = ["Existence", "DOI match", "Retraction", "Claim support", "Hidden text", "Peer-review panel"] as const;
export const scholarlySources = ["Crossref", "OpenAlex", "arXiv", "PubMed", "Retraction Watch"] as const;
