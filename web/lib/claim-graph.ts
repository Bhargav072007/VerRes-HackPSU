import dagre from "dagre";
import type { Edge, Node } from "@xyflow/react";
import type { components } from "./api-types";
import { citationSupportVerdict, referenceVerdict, verifiedEvidence, type Report, type Verdict } from "./report";

type Claim = components["schemas"]["ClaimNode"];
export type Receipt = { citationId: string; claim: string; source: string; sourceFlag?: Verdict; verdict: Verdict; quotes: components["schemas"]["EvidenceSpan"][]; reason: string };
export type GraphData = { label: string; kind: string; receipts: Receipt[]; flag?: Verdict; verdict?: Verdict; note?: string };
export type GraphNode = Node<GraphData>;
export type GraphEdge = Edge<GraphData>;

export function claimGraph(report: Report) {
  const claims = [...new Map((report.claim_map?.nodes ?? []).map(n => [n.id, n])).values()];
  const nodes: GraphNode[] = [], edges: GraphEdge[] = [];
  const citations = report.paper?.citations ?? [], references = report.paper?.references ?? [];
  const linked = (n: Claim) => citations.filter(c => n.citation_ids ? n.citation_ids.includes(c.id) : c.sentence_ids?.some(id => n.sentence_ids?.includes(id)));
  const receiptsByCitation = new Map(citations.map(c => {
    const flag = referenceVerdict(report, c.reference_id);
    const receipt: Receipt = { citationId: c.id,
      claim: report.paper?.sentences?.filter(s => c.sentence_ids?.includes(s.id)).map(s => s.text).join(" ") || c.claim_text || "Claim unavailable. Needs review.",
      source: references.find(r => r.id === c.reference_id)?.title || references.find(r => r.id === c.reference_id)?.raw_text || "Source unavailable. Needs review.",
      verdict: citationSupportVerdict(report, c), sourceFlag: ["RETRACTED", "NOT_FOUND", "DOI_MISMATCH"].includes(flag) ? flag : undefined,
      quotes: verifiedEvidence(report, c), reason: report.support?.find(s => s.citation_id === c.id)?.reason || "Claim support check incomplete. Needs review." };
    const sourceId = `source:${c.reference_id}`;
    let source = nodes.find(node => node.id === sourceId);
    if (!source) {
      source = { id: sourceId, type: "receipt", position: { x: 0, y: 0 }, data: { label: receipt.source, kind: "Source", receipts: [], flag: receipt.sourceFlag } };
      nodes.push(source);
    }
    source.data.receipts.push(receipt);
    return [c.id, receipt];
  }));
  for (const n of claims) {
    const receipts = linked(n).map(c => {
      const receipt = receiptsByCitation.get(c.id)!;
      edges.push({ id: `citation:${n.id}:${c.id}`, source: `claim:${n.id}`, target: `source:${c.reference_id}`, type: "receipt", data: { label: receipt.source, kind: "Citation", verdict: receipt.verdict, receipts: [receipt] } });
      return receipt;
    });
    nodes.push({ id: `claim:${n.id}`, type: "receipt", position: { x: 0, y: 0 }, data: { label: n.text, kind: n.kind === "ASSUMPTION" ? "Assumption" : n.kind === "EVIDENCE" ? "Evidence" : "Claim", receipts } });
  }
  let unlinked = false;
  for (const [i, e] of (report.claim_map?.edges ?? []).entries()) {
    const source = nodes.find(n => n.id === `claim:${e.source_id}`), target = nodes.find(n => n.id === `claim:${e.target_id}`);
    if (!source || !target) { unlinked = true; continue; }
    edges.push({ id: `relationship:${i}`, source: source.id, target: target.id, type: "receipt", data: { label: `${source.data.label} → ${target.data.label}`, kind: "Relationship", verdict: "NEEDS_REVIEW", receipts: [...source.data.receipts, ...target.data.receipts], note: `${e.relation.replaceAll("_", " ")}: ${e.reason} This relationship has no citation support verdict. Needs review. Evidence below describes its linked citations.` }, style: { strokeDasharray: "5 5" } });
  }
  const layout = new dagre.graphlib.Graph({ multigraph: true }).setGraph({ rankdir: "LR", ranksep: 110, nodesep: 32 }).setDefaultEdgeLabel(() => ({}));
  nodes.forEach(n => layout.setNode(n.id, { width: 250, height: 150 }));
  edges.forEach(e => layout.setEdge(e.source, e.target, {}, e.id));
  dagre.layout(layout);
  return { nodes: nodes.map(n => { const p = layout.node(n.id); return { ...n, focusable: true, draggable: false, ariaRole: "button", ariaLabel: `${n.data.kind}: ${n.data.label}. Open evidence`, position: { x: p.x - 125, y: p.y - 75 } }; }), edges: edges.map(e => ({ ...e, focusable: true, ariaRole: "button", ariaLabel: `${e.data!.kind}: ${e.data!.label}. ${e.data!.verdict?.replaceAll("_", " ").toLowerCase()}. Open evidence` })), unlinked };
}
