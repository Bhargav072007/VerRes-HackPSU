import { Check, CircleAlert, X } from "lucide-react";
import { citationVerdict, type Report } from "@/lib/report";

export function ReportChecks({ report }: { report: Report }) {
  const refs = report.paper?.references ?? [], citations = report.paper?.citations ?? [];
  const rows = [
    ["Existence", "References traced to their records", refs.map(r => report.existence?.find(e => e.reference_id === r.id)?.status), ["VERIFIED"], ["NOT_FOUND", "DOI_MISMATCH"]],
    ["Retractions", "Retraction notices checked", refs.map(r => report.retractions?.find(e => e.reference_id === r.id)?.status), ["NONE"], ["RETRACTED"]],
    ["Claim support", "Claims compared with verified source quotes", citations.map(c => citationVerdict(report, c)), ["SUPPORTED"], ["PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "RETRACTED", "NOT_FOUND", "DOI_MISMATCH"]],
    ["Hidden text", "Extracted text inspected for hidden instructions", report.hidden_text?.length ? report.hidden_text.map(f => f.kind) : [report.stages?.some(s => s.stage === "hidden_text" && s.status === "COMPLETED") ? "PASSED" : undefined], ["PASSED"], ["PROMPT_INJECTION", "INVISIBLE_TEXT", "SUSPICIOUS_METADATA"]],
  ] as const;
  return <section aria-label="Checks summary" className="report-card mt-6 border bg-white p-5 sm:p-6"><div className="mb-4 flex items-center justify-between"><h2 className="text-sm font-medium">The checks, with receipts.</h2><span className="text-[10px] tracking-widest text-muted-foreground uppercase">Review ledger</span></div>{rows.map(([label, description, statuses, pass, flags], i) => {
    const flagged = statuses.some(s => flags.some(f => f === s)) || label === "Hidden text" && !!report.hidden_text?.some(f => f.kind !== "CHECK_INCOMPLETE");
    const passed = !!statuses.length && statuses.every(s => pass.some(p => p === s));
    const status = flagged ? "FLAGGED" : passed ? "PASSED" : "NEEDS REVIEW", Icon = flagged ? X : passed ? Check : CircleAlert;
    return <div key={label} className="check-row flex items-center gap-3 border-t py-3.5" style={{ animationDelay: `${i * 60}ms` }}><span className="flex size-6 shrink-0 items-center justify-center rounded-full" style={{ color: flagged ? "var(--red)" : passed ? "var(--sage-text)" : "var(--muted-foreground)", background: flagged ? "var(--red-tint)" : passed ? "var(--sage-tint)" : "var(--cloud)" }}><Icon size={12} aria-hidden /></span><div className="min-w-0 flex-1"><h3 className="text-xs font-medium">{label}</h3><p className="mt-0.5 hidden text-[11px] text-muted-foreground sm:block">{description}</p></div><span className="rounded-full px-2 py-1 text-[9px] font-medium tracking-wide" style={{ color: flagged ? "var(--red)" : passed ? "var(--sage-text)" : "var(--muted-foreground)", background: flagged ? "var(--red-tint)" : passed ? "var(--sage-tint)" : "var(--cloud)" }}>{status}</span></div>;
  })}<p className="mt-2 text-[11px] leading-5 text-muted-foreground">A passed check covers only the evidence available. Incomplete checks stay open for review.</p></section>;
}
