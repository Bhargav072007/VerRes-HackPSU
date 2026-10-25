"use client";
import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { CircleAlert, LoaderCircle } from "lucide-react";
import { Button } from "./ui/button";
import { createJob, parseIdentifier, validatePdf, type ApiError } from "@/lib/api";
import { LandingChrome, StickyNav, receiptNavigate } from "./landing-chrome";
import { LandingScene } from "./landing-scene";
import { LandingResults } from "./landing-results";
import { LandingStepper } from "./landing-stepper";
import { LandingPhone } from "./landing-phone";
import { BlurHeading, CountOnce, Reveal } from "./editorial-motion";
import { Brand } from "./brand";
import { DotMatrix } from "./dot-matrix";
import { recordedStats, productChecks, scholarlySources } from "@/lib/landing-data";
const samples = [
  ["Attention Is All You Need", "paper1_attention.pdf"],
  ["Cites a retracted paper", "paper2_retracted_reference.pdf"],
  ["Planted problems", "paper3_planted_problems.pdf"],
] as const;

export function Landing() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  function chooseFile(files: FileList | null) {
    if (busy || !files?.length) return;
    const message =
      files.length > 1
        ? "Please choose one PDF at a time."
        : validatePdf(files[0]);
    setFile(message ? null : files[0]);
    setIdentifier("");
    setError(message ? { code: "file_invalid", message } : null);
    if (input.current) input.current.value = "";
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!file && !parseIdentifier(identifier)) {
      setError({
        code: "identifier_invalid",
        message: identifier.trim()
          ? "Enter an arXiv ID or DOI"
          : "Choose a PDF or enter an arXiv ID or DOI.",
      });
      return;
    }
    setError(null);
    setBusy(true);
    const result = await createJob(file ? { file } : { identifier });
    if (result.ok) receiptNavigate(router.push, `/check/${encodeURIComponent(result.job_id)}`);
    else {
      setError(result.error);
      setBusy(false);
    }
  }

  async function trySample(filename: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/samples/${filename}`, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error("Sample unavailable");
      const file = new File([await response.blob()], filename, { type: "application/pdf" });
      const result = await createJob({ file });
      if (result.ok) receiptNavigate(router.push, `/check/${encodeURIComponent(result.job_id)}`);
      else { setError(result.error); setBusy(false); }
    } catch {
      setError({ code: "CHECK_INCOMPLETE", message: "This sample could not be loaded. Try again or upload your own PDF." });
      setBusy(false);
    }
  }

return <main id="main" className="landing polished-page"><LandingChrome /><StickyNav /><LandingScene />
<section className="trust-band section-container" aria-label="Product facts">{["tl", "tr", "bl", "br"].map(corner => <span key={corner} aria-hidden className="crosshair" data-corner={corner} />)}<div className="trust-columns"><div><span className="large-numeral"><CountOnce value={productChecks.length} /></span><p>checks per citation</p><div className="tiny-dots" aria-hidden>{productChecks.map(check => <span key={check} />)}</div></div><div><span className="large-numeral"><CountOnce value={scholarlySources.length} /></span><p>scholarly sources</p><div className="tiny-dots" aria-hidden>{scholarlySources.map(source => <span key={source} />)}</div></div>{recordedStats.medianSeconds != null && <div><span className="large-numeral"><CountOnce value={recordedStats.medianSeconds} /><small> s</small></span><p>median review time, recorded runs</p><div className="tiny-bars" aria-hidden><span style={{width:`${Math.min(100,recordedStats.medianSeconds)}%`}} /></div></div>}</div></section>
<LandingStepper />
<Reveal><LandingResults /></Reveal>
<LandingPhone />
<section id="honesty" className="article-section section-container limitations"><BlurHeading className="editorial-title">What we won’t guess.</BlurHeading><p>A missing source, an abstract without enough detail, or an unverifiable quote leaves a question open. A review is a reading aid; judgment remains with the author.</p><ul aria-label="Cases that need review"><li>Source text is unavailable.</li><li>The retrieved abstract does not address the claim.</li><li>The quoted passage cannot be verified.</li><li>The reference identity is ambiguous.</li></ul><p>These findings return <span className="needs-review">Needs review</span>, with the reason available for inspection.</p></section>
<section id="submit" className="upload-band" aria-labelledby="upload-heading"><div className="upload-content section-container"><div className="upload-slip"><div><h2 id="upload-heading">Careful work deserves<br />a careful review.</h2><p>One paper. Citations, claims, a claim graph, an AI peer-review panel, and a scan for hidden prompts.</p></div>      <form
        onSubmit={submit}
        className="upload-form"
        aria-label="Submit a paper"
        aria-busy={busy}
      >
        <section className="upload-card"
        >
          <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-medium">
              Give your paper a second look.
            </h2>
          </div>
          <div
            className="drop-zone"
            data-dragging={dragging}
            onDragOver={(event) => {
              event.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragLeave={(event) => {
              if (
                !event.currentTarget.contains(
                  event.relatedTarget as Node | null,
                )
              )
                setDragging(false);
            }}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              chooseFile(event.dataTransfer.files);
            }}
          >
            <input
              ref={input}
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              tabIndex={-1}
              aria-label="Choose a PDF"
              disabled={busy}
              onChange={(event) => chooseFile(event.currentTarget.files)}
            />
            <button
              type="button"
              disabled={busy}
              onClick={() => input.current?.click()}
              aria-describedby="file-hint submission-error"
              className="flex w-full flex-col items-center rounded-md px-4 py-7 focus-visible:-outline-offset-4 disabled:cursor-wait"
            >
              
              <span className="max-w-full truncate text-sm font-medium">
                {file ? file.name : "Choose PDF"}
              </span>
              <span className="mt-1.5 text-xs text-muted-foreground">
                {file ? (
                  "Click to choose another PDF"
                ) : (
                  <>
                    or{" "}
                    <span className="underline decoration-[#b9bcb2] underline-offset-4">
                      browse files
                    </span>
                  </>
                )}
              </span>
              <span
                id="file-hint"
                className="mt-4 text-xs tracking-wide text-muted-foreground"
              >
                PDF · ≤20 pages · Up to 25MB
              </span>
            </button>
          </div>
          <p className="mt-3 flex items-center justify-center gap-1.5 text-center text-xs leading-4 text-muted-foreground">
            
            Your paper is private and deleted after 7 days.
          </p>
          <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            or use an identifier
            <span className="h-px flex-1 bg-border" />
          </div>
          <label
            htmlFor="identifier"
            className="mb-2 block text-xs font-medium"
          >
            arXiv ID or DOI
          </label>
          <input
            id="identifier"
            name="identifier"
            value={identifier}
            disabled={busy}
            aria-invalid={error?.code === "identifier_invalid"}
            aria-describedby="submission-error"
            onChange={(event) => {
              setIdentifier(event.target.value);
              setFile(null);
              setError(null);
            }}
            placeholder="2401.12345 or 10.1000/xyz"
            className="identifier-input"
            onBlur={() => { if (identifier.trim() && !parseIdentifier(identifier)) setError({ code: "identifier_invalid", message: "Enter an arXiv ID or DOI" }); }}
          />
          {error && (
            <p
              id="submission-error"
              role="alert"
              className="mt-3 flex items-start gap-2 text-xs leading-5"
            >
              <CircleAlert size={15} className="mt-0.5 shrink-0" />
              <span>{error.message}</span>
            </p>
          )}
          <Button
            type="submit"
            disabled={busy}
            className="submit-button"
          >
            {busy ? (
              <>
                <LoaderCircle
                  size={14}
                  className=""
                />{" "}
                Starting review…
              </>
            ) : (
              <>
                Review my paper 
              </>
            )}
          </Button>
        </section>
        <div className="sample-papers">
          <span className="sample-heading eyebrow">
            Try a sample
          </span>
          {samples.map(
            ([label, filename]) => (
              <Button
                key={filename}
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => void trySample(filename)}
                className="sample-card"
                aria-label={label}
              >
                <span><strong>{label}</strong></span>
              </Button>
            ),
          )}
        </div>
      </form></div><DotMatrix /></div></section><footer className="site-footer"><div className="journal-colophon section-container"><Brand /><p>{scholarlySources.join(" · ")} · GROBID</p><a href="https://github.com/Bhargav072007/VerRes-HackPSU">GitHub</a></div><p className="footer-wordmark" aria-hidden>VerRes</p></footer></main>;
}
