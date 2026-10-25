"use client";
import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import type { Report } from "@/lib/report";

export function HiddenText({ findings }: { findings: Report["hidden_text"] }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  if (!findings?.length) return null;
  const pages = Map.groupBy(findings, f => Number.isInteger(f.page) && f.page! > 0 ? f.page! : null);
  const incomplete = findings.every(f => f.kind === "CHECK_INCOMPLETE");
  return <section aria-label="Hidden text findings" className="report-card mb-6 rounded-md border bg-white p-6" style={{ borderColor: incomplete ? "var(--blue-ink)" : "#b42318" }}>
    <h2 className={`flex items-center gap-2 text-sm font-medium ${incomplete ? "text-[var(--blue-ink)]" : "text-destructive"}`}><AlertTriangle size={18} aria-hidden />{incomplete ? "Hidden-text check incomplete · Needs review" : "Hidden instructions found"}</h2>
    <p className="mt-2 text-xs leading-6 text-muted-foreground">Hidden instructions can be invisible to humans, read by AI reviewers.</p>
    {[...pages].sort(([a], [b]) => (a ?? Infinity) - (b ?? Infinity)).map(([page, items]) => <section key={page ?? "unknown"} aria-label={page ? `Page ${page}` : "Page unavailable"} className="mt-5 border-t pt-4"><h3 className="text-xs font-medium">{page ? `Page ${page}` : "Page unavailable"}</h3>{items.map((f, i) => {
      const key = `${page}-${i}`, quote = typeof f.quote === "string" ? f.quote : "Extracted text unavailable. Needs review.";
      return <div key={key} className="mt-3"><pre id={`hidden-${key}`} className={`xray-panel whitespace-pre-wrap font-mono text-xs leading-6 break-all ${expanded[key] ? "" : "line-clamp-3"}`}>{quote || "No extracted text available. Needs review."}</pre><button aria-expanded={!!expanded[key]} aria-controls={`hidden-${key}`} onClick={() => setExpanded({ ...expanded, [key]: !expanded[key] })} className="mt-2 text-xs underline underline-offset-4">{expanded[key] ? "Collapse extracted text" : "Expand extracted text"}</button>{typeof f.reason === "string" && <p className="mt-2 text-xs leading-5 text-muted-foreground">{f.reason}</p>}</div>;
    })}</section>)}
  </section>;
}
