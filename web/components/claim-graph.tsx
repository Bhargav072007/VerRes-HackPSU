"use client";
import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ReactFlow, Controls, Handle, Position, BaseEdge, getBezierPath, type NodeProps, type EdgeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion, useReducedMotion } from "motion/react";
import { claimGraph, type GraphData, type GraphNode, type GraphEdge } from "@/lib/claim-graph";
import { motionTokens } from "@/lib/motion";
import type { Report } from "@/lib/report";
import { VerdictBadge, verdicts } from "./verdict-badge";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "./ui/sheet";

function ReceiptNode({ data }: NodeProps<GraphNode>) {
  return <div className="h-[150px] w-[250px] rounded-xl border bg-white p-4 text-left" style={data.flag ? { borderColor: "#b42318", borderWidth: 2 } : undefined}>
    <Handle type="target" position={Position.Left} isConnectable={false} />
    <p className="mb-2 text-[10px] tracking-wider text-muted-foreground uppercase">{data.kind}</p>
    <p className={`line-clamp-3 text-sm leading-5 ${data.kind === "Source" ? "" : "font-serif"}`}>{data.label}</p>
    {data.flag && <div className="mt-2"><VerdictBadge status={data.flag} /></div>}
    <Handle type="source" position={Position.Right} isConnectable={false} />
  </div>;
}
function ReceiptEdge(props: EdgeProps<GraphEdge>) {
  const reduced = useReducedMotion(), [path, x, y] = getBezierPath(props);
  const [label, color, Icon] = verdicts[props.data?.verdict ?? "NEEDS_REVIEW"];
  return <motion.g initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={reduced ? { duration: 0 } : motionTokens.fade}>
    <BaseEdge id={props.id} path={path} style={{ ...props.style, stroke: color, strokeWidth: 2 }} interactionWidth={30} />
    <title>{label} · {props.data?.kind}</title>
    <foreignObject x={x - 10} y={y - 10} width={20} height={20} pointerEvents="none"><span style={{ color }} className="flex size-5 items-center justify-center rounded-full border bg-white"><Icon size={12} aria-hidden /></span></foreignObject>
  </motion.g>;
}
const nodeTypes = { receipt: ReceiptNode }, edgeTypes = { receipt: ReceiptEdge };
const smallScreen = () => window.matchMedia("(max-width: 639px)").matches;
const subscribe = (change: () => void) => { const query = window.matchMedia("(max-width: 639px)"); query.addEventListener("change", change); return () => query.removeEventListener("change", change); };

export function ClaimGraph({ report, onOpenEvidence }: { report: Report; onOpenEvidence: (id: string) => void }) {
  const graph = useMemo(() => claimGraph(report), [report]);
  const mobile = useSyncExternalStore(subscribe, smallScreen, () => true);
  const [selection, setSelection] = useState<GraphData | null>(null);
  const jump = useRef("");
  const pending = report.claim_map?.status === "NEEDS_REVIEW";
  return <section aria-label="Claim graph" className="overflow-hidden rounded-xl border bg-white">
    <header className="border-b p-5 sm:p-6"><h2 className="font-serif text-2xl">Claim graph</h2><p className="mt-2 text-xs leading-5 text-muted-foreground">Follow each claim to its cited sources. Select a claim, source, or connection to inspect its receipts.</p>
      <div aria-label="Graph legend" className="mt-4 flex flex-wrap gap-2">{["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "NEEDS_REVIEW"].map(status => <VerdictBadge key={status} status={status} />)}</div>
      {(pending || graph.unlinked) && <p role="status" className="mt-4 text-sm"><VerdictBadge /> {report.claim_map?.needs_review_reason || (graph.unlinked ? "Some claim relationships could not be linked. Inspect the available receipts." : "The claim map is incomplete. Inspect the available receipts.")}</p>}
    </header>
    {!graph.nodes.length ? <p className="p-8 text-sm text-muted-foreground">No claims extracted</p> : mobile ? <ul aria-label="Claim graph list" className="space-y-4 p-5">
      {graph.nodes.filter(n => n.data.kind !== "Source").map(n => <li key={n.id} className="rounded-xl border p-4"><button className="w-full text-left font-serif text-lg" onClick={() => setSelection(n.data)}>{n.data.label}</button><ul className="mt-4 space-y-3">
        {n.data.receipts.map(r => <li key={r.citationId}><button className="w-full rounded-lg border p-3 text-left" style={r.sourceFlag ? { borderColor: "#b42318" } : undefined} onClick={() => setSelection({ label: r.source, kind: "Citation", receipts: [r] })}><span className="mb-2 block text-xs">{r.source}</span><span className="flex flex-wrap gap-2"><VerdictBadge status={r.verdict} />{r.sourceFlag && <VerdictBadge status={r.sourceFlag} />}</span></button></li>)}
      </ul></li>)}
      {graph.edges.filter(e => e.data?.kind === "Relationship").map(e => <li key={e.id}><button className="w-full rounded-xl border p-4 text-left text-sm" onClick={() => setSelection(e.data!)}><span className="mb-2 block">{e.data!.label}</span><VerdictBadge /></button></li>)}
    </ul> : <div className="h-[580px]" data-testid="claim-graph-canvas" onKeyDownCapture={e => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const id = (e.target as Element).closest("[data-id]")?.getAttribute("data-id"), data = graph.nodes.find(n => n.id === id)?.data ?? graph.edges.find(edge => edge.id === id)?.data;
      if (data) { e.preventDefault(); e.stopPropagation(); setSelection(data); }
    }}><ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: .15 }} minZoom={.25} maxZoom={1.5} nodesConnectable={false} nodesDraggable={false} edgesReconnectable={false} deleteKeyCode={null} onNodeClick={(_, n) => setSelection(n.data)} onEdgeClick={(_, e) => setSelection(e.data ?? null)}><Controls showInteractive={false} /></ReactFlow></div>}
    <Sheet open={!!selection} onOpenChange={open => { if (!open) setSelection(null); }}><SheetContent className="w-full overflow-y-auto p-6 sm:max-w-lg" onCloseAutoFocus={e => { if (jump.current) { e.preventDefault(); const id = jump.current; jump.current = ""; onOpenEvidence(id); } }}>
      <SheetTitle className="font-serif text-2xl">Claim receipt</SheetTitle><SheetDescription>Select a receipt to follow it into the evidence panel.</SheetDescription>
      {selection && <><p className="text-xs text-muted-foreground">{selection.kind}</p><p className="font-serif text-lg leading-7">{selection.label}</p>{selection.flag && <VerdictBadge status={selection.flag} />}{selection.note && <p className="text-sm leading-6"><VerdictBadge /> {selection.note}</p>}
        {!selection.receipts.length && <p className="text-sm"><VerdictBadge /> No linked citation or verified source quote available.</p>}
        {selection.receipts.map((r, i) => <section key={`${r.citationId}:${i}`} className="space-y-4 rounded-xl border bg-white p-5"><VerdictBadge status={r.verdict} /><h3 className="text-xs text-muted-foreground">Claim sentence</h3><p className="font-serif leading-7">{r.claim}</p><h3 className="text-xs text-muted-foreground">Source</h3><p className="text-sm">{r.source}</p>{r.sourceFlag && <VerdictBadge status={r.sourceFlag} />}<h3 className="text-xs text-muted-foreground">Verified quote</h3>{r.quotes.length ? r.quotes.map((q, j) => <blockquote key={j} className="border-l-2 pl-3 font-serif leading-7">“{q.quote}”<span className="block font-sans text-[10px] text-muted-foreground">Verified verbatim · {q.passage_id}</span></blockquote>) : <p className="text-sm text-muted-foreground">No verified source quote available. Needs review.</p>}<p className="text-xs leading-6 text-muted-foreground">{r.sourceFlag === "NOT_FOUND" ? "Not found in Crossref, OpenAlex or arXiv." : r.reason}</p><button className="rounded-md border px-3 py-2 text-xs" onClick={() => { jump.current = r.citationId; setSelection(null); }}>Open in evidence panel</button></section>)}
      </>}
    </SheetContent></Sheet>
  </section>;
}
