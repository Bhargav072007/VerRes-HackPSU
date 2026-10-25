"use client";
import { useMemo, useRef, type PointerEvent } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import type { JobState } from "@/lib/job-stream";
import { liveFindings, liveGraph } from "@/lib/live-findings";
import { motionTokens } from "@/lib/motion";
import { verdicts, VerdictBadge } from "./verdict-badge";
import "./live-findings.css";

type Model = ReturnType<typeof liveFindings>;
export function LiveFindings({ model, id, ready, reduced }: { model: Model; id: string; ready: boolean; reduced: boolean }) {
  return <section className="live-findings live-card" aria-labelledby="findings-title">
    <header><h2 id="findings-title">Findings as they arrive.</h2><span>Every finding keeps its receipt.</span></header>
    <div className="finding-window" role="log" aria-live="polite" aria-relevant="additions text">
      {!model.findings.length && <p className="finding-empty">No findings yet.<br /><span>Results will appear here as checks return.</span></p>}
      <ol>{model.findings.slice(0, 5).map((f, i) => <motion.li key={f.id} data-finding={f.id} initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={reduced ? { duration: 0 } : { ...motionTokens.fade, delay: Math.min(i, 4) * motionTokens.stagger }}>
        <div><VerdictBadge status={f.verdict} />{ready ? <Link href={`/report/${encodeURIComponent(id)}${f.citationId ? `?flag=${encodeURIComponent(f.citationId)}` : f.hiddenId ? `#hidden-${encodeURIComponent(f.hiddenId)}` : ""}`}>View receipt →</Link> : <span className="receipt-pending">Receipt in the finished report</span>}</div><p>{f.sentence}</p>
      </motion.li>)}</ol>
    </div>
    <details className="older-findings" hidden={model.findings.length <= 5}><summary>+{Math.max(0, model.findings.length - 5)} more</summary><ul>{model.findings.slice(5).map(f => <li key={f.id}><VerdictBadge status={f.verdict} /><p>{f.sentence}</p>{ready && <Link href={`/report/${encodeURIComponent(id)}${f.citationId ? `?flag=${encodeURIComponent(f.citationId)}` : f.hiddenId ? `#hidden-${encodeURIComponent(f.hiddenId)}` : ""}`}>View receipt →</Link>}</li>)}</ul></details>
  </section>;
}

export function LiveFindingsRail({ state, model, reduced }: { state: JobState; model: Model; reduced: boolean }) {
  const graph = useMemo(() => liveGraph(state, model.report), [state, model.report]);
  const field = useRef<HTMLUListElement>(null);
  const width = Math.max(1, ...graph.nodes.map(n => n.position.x + 250)), height = Math.max(1, ...graph.nodes.map(n => n.position.y + 150));
  function nudge(event?: PointerEvent) {
    for (const dot of field.current?.querySelectorAll<HTMLElement>("[data-dot]") ?? []) {
      if (reduced || !event) { dot.style.transform = "none"; continue; }
      const box = dot.parentElement!.getBoundingClientRect(), dx = box.x + box.width / 2 - event.clientX, dy = box.y + box.height / 2 - event.clientY;
      const distance = Math.hypot(dx, dy), amount = Math.max(0, 1 - distance / 80) * 4;
      dot.style.transform = distance && amount ? `translate(${dx / distance * amount}px, ${dy / distance * amount}px)` : "none";
    }
  }
  return <aside className="live-findings-rail" aria-label="Live evidence overview">
    <section className="live-card mini-graph" aria-label="Live claim graph"><header><h2>Claims taking shape.</h2><span>Claims → cited sources</span></header>
      <div className="mini-graph-canvas">{!graph.nodes.length ? <p className="finding-empty">Waiting for parsed claims.</p> : <svg role="img" aria-label={`${graph.nodes.filter(n => n.data.kind !== "Source").length} parsed claims and their sources`} viewBox={`-20 -20 ${width + 40} ${height + 40}`}>
        {graph.edges.map(e => { const a = graph.nodes.find(n => n.id === e.source)!, b = graph.nodes.find(n => n.id === e.target)!;
          const status = e.data?.verdict ?? "NEEDS_REVIEW", [, color] = verdicts[status];
          return <path key={e.id} data-edge-verdict={status} d={`M${a.position.x + 250},${a.position.y + 75} C${a.position.x + 305},${a.position.y + 75} ${b.position.x - 55},${b.position.y + 75} ${b.position.x},${b.position.y + 75}`} fill="none" stroke={color} strokeWidth={5}><title>{verdicts[status][0]}: {e.data?.label}</title></path>;
        })}
        {graph.nodes.map(n => <motion.g key={n.id} initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={reduced ? { duration: 0 } : motionTokens.fade}><title>{n.data.kind}: {n.data.label}</title><rect x={n.position.x} y={n.position.y} width={250} height={150} rx={24} fill="white" stroke="#706f6c" strokeWidth={3} /><text x={n.position.x + 20} y={n.position.y + 60} fontSize={25} fill="#1b1b19">{n.data.kind}</text><text x={n.position.x + 20} y={n.position.y + 100} fontSize={20} fill="#706f6c">{n.data.label.slice(0, 20)}…</text></motion.g>)}
      </svg>}</div><div className="graph-key">{(["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "NEEDS_REVIEW"] as const).map(v => { const [label, color, Icon] = verdicts[v]; return <span key={v} style={{ color }}><Icon size={10} aria-hidden />{label}</span>; })}</div>
    </section>
    <section className="live-card reference-field" aria-label="Reference dot field"><header><h2>Reference by reference.</h2><span>One dot for each extracted reference.</span></header>
      <div className="dot-window"><ul ref={field} data-static={reduced} onPointerMove={reduced ? undefined : nudge} onPointerLeave={() => nudge()}>{model.dots.map((dot, i) => { const [label, color, Icon] = verdicts[dot.verdict]; return <li key={dot.id} aria-label={`Reference ${i + 1}: ${dot.checked ? label : "Pending"}`} title={`Reference [${i + 1}] · ${dot.checked ? label : "Pending"}`}><span data-dot data-checked={dot.checked} style={{ background: dot.checked ? color : "transparent", borderColor: dot.checked ? color : "#9c9b98" }}>{dot.checked && <Icon size={9} aria-hidden />}</span></li>; })}</ul>
      {!model.dots.length && <p className="finding-empty">Waiting for references.</p>}</div><p className="field-note">Unfilled dots are waiting for a check.</p>
    </section>
  </aside>;
}
