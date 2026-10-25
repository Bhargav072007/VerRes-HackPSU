import type { paths } from "./api-types";
import { decodeReport } from "./report";

type Share = paths["/jobs/{job_id}/share"]["post"]["responses"][200]["content"]["application/json"];
export function reportUrl(id: string, shared = false) {
  const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
  return `${base}/${shared ? "shares" : "jobs"}/${encodeURIComponent(id)}`;
}
export async function createShare(id: string): Promise<{ share: Share; error?: never } | { share?: never; error: string }> {
  try {
    const response = await fetch(`${reportUrl(id)}/share`, { method: "POST", signal: AbortSignal.timeout(10_000) });
    if (!response.ok) return { error: response.status === 429 ? "Too many share requests. Please try again later." : "The share link could not be created. Please try again." };
    const value: Share = await response.json();
    const url = new URL(value.url);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || typeof value.token !== "string" || !Number.isFinite(Date.parse(value.expires_at))) return { error: "The share response could not be read. Please try again." };
    return { share: value };
  } catch { return { error: "The share link could not be created. Please try again." }; }
}
export async function loadSharedReport(token: string, signal: AbortSignal) {
  try {
    const response = await fetch(reportUrl(token, true), { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]) });
    return { report: response.ok ? decodeReport(await response.json()) : null, expired: response.status === 410 };
  } catch { return { report: null, expired: false }; }
}
