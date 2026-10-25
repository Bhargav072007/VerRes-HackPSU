"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import {
  ArrowRight,
  FileText,
  Upload,
  LockKeyhole,
  ScanText,
  Quote,
  Network,
  CircleAlert,
  LoaderCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  createJob,
  parseIdentifier,
  validatePdf,
  type ApiError,
} from "@/lib/api";
import { motionTokens } from "@/lib/motion";
import { LandingChrome, receiptNavigate, usePolishMotion } from "./landing-chrome";
import { LandingScene, DemoStats } from "./landing-scene";

const samples = [
  ["Attention Is All You Need", "paper1_attention.pdf"],
  ["Cites a retracted paper", "paper2_retracted_reference.pdf"],
  ["Planted problems", "paper3_planted_problems.pdf"],
] as const;

const features = [
  {
    icon: ScanText,
    title: "Check the references.",
    text: "Trace citations to real sources and check for retractions.",
  },
  {
    icon: Quote,
    title: "Follow the evidence.",
    text: "Test claims against sources, with verbatim quotes you can inspect.",
  },
  {
    icon: Network,
    title: "See the whole paper.",
    text: "Map the claims, hear a review panel, and flag hidden prompts.",
  },
];

export function Landing() {
  const router = useRouter();
  const reduced = usePolishMotion();
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

  return (
    <main
      id="main"
      className="landing polished-page"
    >
      <LandingChrome />
      <LandingScene />
      <div className="section-container"><DemoStats /></div>
      <section id="submit" data-section="01 · UPLOAD" className="section-container numbered-section" aria-labelledby="upload-heading">
        <span className="section-number" aria-hidden="true">01</span>
        <div className="section-heading" data-enter><div><p className="section-pill">● 01 · Upload</p><h2 id="upload-heading">Your paper.<br />A second look.</h2></div><p>Bring the work you care about.<br />We’ll follow the references, inspect the claims, and <strong>leave a trail you can check.</strong></p></div>
        <div className="upload-grid"><aside className="upload-aside" data-enter><p className="eyebrow">BEFORE THE NEXT SUBMISSION</p><h3>Careful work deserves<br />a careful review.</h3><p>One paper. Citations, claims, a claim graph, an AI peer-review panel, and a scan for hidden prompts.</p><ol><li><span>01</span>Upload a PDF or paste an identifier.</li><li><span>02</span>Follow each check as it happens.</li><li><span>03</span>Open the findings. Inspect the receipts.</li></ol><p className="privacy-note"><LockKeyhole size={13} /> Private. Deleted after 7 days.</p></aside>
      <form
        onSubmit={submit}
        className="upload-form"
        aria-label="Submit a paper"
        aria-busy={busy}
      >
        <motion.section
          layoutId="job"
          transition={reduced ? { duration: 0 } : motionTokens.layout}
          className="upload-card crosshair"
        >
          <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-medium">
              Give your paper a second look.
            </h2>
            <span className="text-[9px] tracking-[.14em] text-muted-foreground">
              01 / SUBMIT
            </span>
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
            <span className="shimmer" aria-hidden="true" />
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
              className="flex w-full flex-col items-center rounded-lg px-4 py-7 focus-visible:-outline-offset-4 disabled:cursor-wait"
            >
              <span className="file-type-icon" key={file ? "file" : "upload"}>
                {file ? (
                  <FileText size={19} strokeWidth={1.4} />
                ) : (
                  <Upload size={19} strokeWidth={1.4} />
                )}
              </span>
              <span className="max-w-full truncate text-sm font-medium">
                {file ? file.name : "Drop your paper here"}
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
                className="mt-4 text-[10px] tracking-wide text-muted-foreground"
              >
                PDF only · Up to 25MB
              </span>
            </button>
          </div>
          <p className="mt-3 flex items-center justify-center gap-1.5 text-center text-[10px] leading-4 text-muted-foreground">
            <LockKeyhole size={11} className="shrink-0" />
            Your paper is private and deleted after 7 days.
          </p>
          <div className="my-5 flex items-center gap-3 text-[10px] text-muted-foreground">
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
                  className="animate-[spin_360ms_linear_infinite]"
                />{" "}
                Starting review…
              </>
            ) : (
              <>
                Review my paper <ArrowRight size={14} />
              </>
            )}
          </Button>
          <p className="mt-3 text-center text-[10px] text-muted-foreground">
            Every finding comes with evidence you can verify.
          </p>
        </motion.section>
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
                <FileText size={17} strokeWidth={1.3} /><span><span className="eyebrow">SAMPLE PAPER</span><strong>{label}</strong></span><ArrowRight className="size-3" />
              </Button>
            ),
          )}
        </div>
      </form>

      </div></section>
      <section id="how-it-works" data-section="02 · THE CHECKS" className="white-sheet numbered-section" aria-labelledby="checks-heading">
        <div className="section-container"><span className="section-number" aria-hidden="true">02</span><div className="section-heading" data-enter><div><p className="section-pill">● 02 · The checks</p><h2 id="checks-heading">Every finding.<br />A paper trail.</h2></div><p>A reference should exist. A source should support the claim. <strong>You should be able to see exactly why.</strong></p></div>
        <div className="feature-grid">{features.map(({ icon: Icon, title, text }, i) => <article className="feature-card crosshair" key={title} data-enter style={{ transitionDelay: `${i * 80}ms` }}><div><Icon size={22} strokeWidth={1.3} /><span className="eyebrow">0{i + 1}</span></div><h3>{title}</h3><p>{text}</p><span className="feature-receipt">↳ Evidence included</span></article>)}</div></div>
      </section>
      <section id="honesty" data-section="03 · OUR PRINCIPLE" className="section-container numbered-section honesty-section" aria-labelledby="honesty-heading"><span className="section-number" aria-hidden="true">03</span><div className="section-heading" data-enter><div><p className="section-pill">● 03 · Our principle</p><h2 id="honesty-heading" className="unblur">What we<br />won’t guess.</h2></div><p>Missing evidence is a reason to pause.<br /><strong>Receipts, not scores.</strong> Every verdict explains what we found — and what we couldn’t verify.</p></div><article className="honesty-card crosshair" data-enter><div><p className="eyebrow">ILLUSTRATIVE FINDING / CLAIM 04</p><h3>Does the source support this claim?</h3><p>We couldn’t retrieve the full source text. The abstract alone isn’t enough to verify this claim.</p></div><div><span className="status-pill blue">? NEEDS_REVIEW</span><p>Next step: inspect the full paper and the cited passage before submission.</p></div></article></section>
      <footer className="landing-footer"><div className="section-container"><div className="footer-top"><div><p className="section-pill">A LITTLE SCRUTINY GOES A LONG WAY</p><h2>Submit with receipts.</h2></div><a className="pill-button" href="#submit">Review your paper <ArrowRight size={15} /></a></div><div className="footer-meta"><span>VerRes · Research deserves a second look.</span><a href="#honesty">Receipts, not scores.</a></div></div><span className="footer-wordmark" aria-hidden="true">VerRes</span></footer>
    </main>
  );
}
