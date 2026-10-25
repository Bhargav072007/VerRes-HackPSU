"use client";
import { motion } from "motion/react";
import { usePolishMotion } from "./landing-chrome";
import { Check, CircleAlert, Minus, X } from "lucide-react";

export const verdicts = {
  SUPPORTED: ["Supported", "#3F6B4F", Check], VERIFIED: ["Verified", "#3F6B4F", Check], NONE: ["No retraction found", "#3F6B4F", Check],
  PARTIALLY_SUPPORTED: ["Partially supported", "#8A6B25", Minus], NOT_SUPPORTED: ["Not supported", "#b42318", X], CONTRADICTED: ["Contradicted", "#b42318", X],
  NOT_FOUND: ["Not found", "#b42318", X], DOI_MISMATCH: ["DOI mismatch", "#b42318", CircleAlert], RETRACTED: ["Retracted", "#b42318", CircleAlert],
  NEEDS_REVIEW: ["Needs review", "#46677A", CircleAlert],
} as const;
export function VerdictBadge({ status }: { status?: string }) {
  const reduced = usePolishMotion();
  const [label, color, Icon] = status && Object.hasOwn(verdicts, status) ? verdicts[status as keyof typeof verdicts] : verdicts.NEEDS_REVIEW;
  return <motion.span initial={reduced ? false : {scale:.96}} whileInView={{scale:1}} viewport={{once:true}} transition={{duration:reduced?0:.16}} data-critical={["NOT_SUPPORTED", "NOT_FOUND", "CONTRADICTED", "RETRACTED", "DOI_MISMATCH"].includes(status || "")} className="verdict-chip inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium" style={{ color: `var(--verdict-${status}, ${status === "PARTIALLY_SUPPORTED" ? "var(--foreground)" : color})` }}><Icon size={12} style={{ color: `var(--verdict-${status}, ${color})` }} aria-hidden /><span className="verdict-label">{label}</span></motion.span>;
}
