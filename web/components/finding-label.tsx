import { Ban, CircleCheck, CircleDashed, CircleHelp, CircleX, Link2Off, SearchX, type LucideIcon } from "lucide-react";
import { findingStyles, type HeroChip } from "@/lib/landing-data";
// One look for a reference finding everywhere it appears: hero paper, review room and its feed.
export const findingIcons: Record<HeroChip, LucideIcon> = { SUPPORTED: CircleCheck, PARTIALLY_SUPPORTED: CircleDashed, NOT_SUPPORTED: CircleX, CONTRADICTED: CircleX, NOT_FOUND: SearchX, DOI_MISMATCH: Link2Off, RETRACTED: Ban, NEEDS_REVIEW: CircleHelp };
export function Finding({ chip, children }: { chip: HeroChip; children?: React.ReactNode }) {
  const { label, color, text } = findingStyles[chip], Icon = findingIcons[chip];
  return <span className="finding-label" data-chip={chip} style={{ color: `var(--finding-${chip}, ${text})` }}><Icon size={15} aria-hidden style={{ color: `var(--finding-bar-${chip}, ${color})` }} />{label}{children}</span>;
}
