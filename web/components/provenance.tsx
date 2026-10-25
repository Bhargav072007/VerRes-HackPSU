import type { components } from "@/lib/api-types";

export function Provenance({ label, value }: { label: string; value?: Partial<Pick<components["schemas"]["EvidenceSpan"], "source_url" | "retrieved_at" | "evidence_level" | "model_id">> | null }) {
  if (!value) return null;
  const fields = [["Retrieved at", value.retrieved_at], ["Evidence level", value.evidence_level], ["Model ID", value.model_id]].filter((field): field is [string, string] => typeof field[1] === "string" && !!field[1]);
  const url = typeof value.source_url === "string" && URL.canParse(value.source_url) ? new URL(value.source_url) : null;
  const href = url && ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  if (!href && !fields.length) return null;
  return <section aria-label={`${label} provenance`} className="mt-4 rounded-md border bg-white/60 p-4 text-xs leading-6"><h3 className="font-medium">{label} provenance</h3><dl className="mt-2 grid gap-3 break-words sm:grid-cols-2">{href && <div><dt className="text-muted-foreground">Source</dt><dd><a href={href} target="_blank" rel="noreferrer" className="break-all underline">{href}</a></dd></div>}{fields.map(([name, text]) => <div key={name}><dt className="text-muted-foreground">{name}</dt><dd>{text}</dd></div>)}</dl></section>;
}
