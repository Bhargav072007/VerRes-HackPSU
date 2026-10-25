import { Check, CircleAlert, Minus, X } from "lucide-react";

export const verdicts = {
  SUPPORTED: ["Supported", "#2f7d4f", Check], VERIFIED: ["Verified", "#2f7d4f", Check], NONE: ["No retraction found", "#2f7d4f", Check],
  PARTIALLY_SUPPORTED: ["Partially supported", "#b7791f", Minus], NOT_SUPPORTED: ["Not supported", "#b42318", X], CONTRADICTED: ["Contradicted", "#b42318", X],
  NOT_FOUND: ["Not found", "#b42318", X], DOI_MISMATCH: ["DOI mismatch", "#b42318", CircleAlert], RETRACTED: ["Retracted", "#b42318", CircleAlert],
  NEEDS_REVIEW: ["Needs review", "#5b6b8c", CircleAlert],
} as const;
export function VerdictBadge({ status }: { status?: string }) {
  const [label, color, Icon] = status && Object.hasOwn(verdicts, status) ? verdicts[status as keyof typeof verdicts] : verdicts.NEEDS_REVIEW;
  return <span data-critical={["NOT_SUPPORTED", "NOT_FOUND", "CONTRADICTED", "RETRACTED", "DOI_MISMATCH"].includes(status || "")} className="verdict-chip inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-medium" style={{ color: `var(--verdict-${status}, ${status === "PARTIALLY_SUPPORTED" ? "var(--foreground)" : color})` }}><Icon size={12} style={{ color: `var(--verdict-${status}, ${color})` }} aria-hidden />{label}</span>;
}
