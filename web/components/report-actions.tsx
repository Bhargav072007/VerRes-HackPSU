"use client";
import { useState } from "react";
import { DropdownMenu, Popover } from "radix-ui";
import { Check, Copy, Download, Share2 } from "lucide-react";
import { createShare, reportUrl } from "@/lib/sharing";

export function ReportActions({ id, shared }: { id: string; shared: boolean }) {
  const [result, setResult] = useState<Awaited<ReturnType<typeof createShare>> | null>(null);
  const [busy, setBusy] = useState(false), [copied, setCopied] = useState(false), [copyError, setCopyError] = useState("");
  const [exportError, setExportError] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  async function share() {
    if (result?.share || busy) return;
    setBusy(true); setResult(null); setResult(await createShare(id)); setBusy(false);
  }
  async function copy() {
    if (!result?.share) return;
    try { await navigator.clipboard.writeText(result.share.url); setCopied(true); setCopyError(""); }
    catch { setCopyError("Copy unavailable. Select and copy the link above."); }
  }
  async function download(event: React.MouseEvent<HTMLAnchorElement>, format: string) {
    event.preventDefault(); setExportError(""); setExportOpen(false);
    try {
      const response = await fetch(event.currentTarget.href, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) { setExportError(response.status === 410 ? "This link expired or was revoked" : "The export could not be downloaded. Please try again."); return; }
      const url = URL.createObjectURL(await response.blob()), link = document.createElement("a");
      link.href = url; link.download = `verres-receipt.${format}`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setExportError("The export could not be downloaded. Please try again."); }
  }
  return <div className="flex flex-wrap items-center justify-end gap-2">
    {!shared && <Popover.Root onOpenChange={open => { if (open) void share(); }}><Popover.Trigger className="inline-flex items-center gap-2 rounded-lg border bg-white px-3 py-2 text-xs"><Share2 size={14} aria-hidden />Share</Popover.Trigger>
      <Popover.Portal><Popover.Content aria-label="Share report" sideOffset={8} align="end" collisionPadding={20} className="report-overlay report-menu z-40 w-80 max-w-[calc(100vw-40px)] rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="font-serif text-xl">Share this report</h2><p className="mt-2 text-xs leading-5 text-muted-foreground">Anyone with the link can read this report.</p>
        {busy && <p role="status" className="mt-4 text-xs">Creating link…</p>}
        {result?.error && <div role="alert" className="mt-4 text-xs leading-5"><p>{result.error}</p><button onClick={() => void share()} className="mt-3 rounded-md border px-3 py-2">{result.retryMinutes ? `Try again in ${result.retryMinutes} min` : "Try again"}</button></div>}
        {result?.share && <><label className="mt-4 block text-xs">Report link<input readOnly value={result.share.url} onFocus={e => e.target.select()} className="mt-2 block w-full rounded-md border p-2 text-xs" /></label><p className="mt-3 text-xs text-muted-foreground">Expires <time dateTime={result.share.expires_at}>{new Date(result.share.expires_at).toLocaleString()}</time></p><button onClick={() => void copy()} className="mt-4 inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs">{copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}{copied ? "Copied" : "Copy link"}</button><p role="status" className="mt-2 text-xs">{copyError || (copied ? "Link copied to clipboard." : "")}</p></>}
      </Popover.Content></Popover.Portal>
    </Popover.Root>}
    <DropdownMenu.Root open={exportOpen} onOpenChange={setExportOpen}><DropdownMenu.Trigger className="inline-flex items-center gap-2 rounded-lg border bg-white px-3 py-2 text-xs"><Download size={14} aria-hidden />Export</DropdownMenu.Trigger><DropdownMenu.Portal><DropdownMenu.Content align="end" sideOffset={8} collisionPadding={20} className="report-overlay report-menu z-40 rounded-xl border bg-white p-1 shadow-sm">{[["json", "Download JSON"], ["md", "Download Markdown receipt"]].map(([format, label]) => <DropdownMenu.Item key={format} asChild><a href={`${reportUrl(id, shared)}/export?format=${format}`} download={`verres-receipt.${format}`} onClick={event => void download(event, format)} className="block rounded-lg px-4 py-3 text-xs outline-none focus:bg-secondary">{label}</a></DropdownMenu.Item>)}</DropdownMenu.Content></DropdownMenu.Portal></DropdownMenu.Root>
    {exportError && <p role="alert" className="w-full text-xs">{exportError}</p>}
  </div>;
}
