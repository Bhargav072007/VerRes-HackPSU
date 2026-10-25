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
  BookOpen,
  ShieldCheck,
  Eye,
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
import { LandingScene } from "./landing-scene";

import { LandingResults } from "./landing-results";
import { Brand } from "./brand";

const samples = [
  ["Attention Is All You Need", "paper1_attention.pdf"],
  ["Cites a retracted paper", "paper2_retracted_reference.pdf"],
  ["Planted problems", "paper3_planted_problems.pdf"],
] as const;

const features = [
  { icon: BookOpen, title: "Reference existence", text: "Resolve each citation through Crossref, OpenAlex, and arXiv.", diagram: "Citation → bibliographic record" },
  { icon: ShieldCheck, title: "Retraction history", text: "Check whether a cited work has been retracted, with a link to the notice.", diagram: "Record → retraction notice" },
  { icon: Quote, title: "Claim support", text: "Compare a claim with a verbatim passage verified against the source.", diagram: "Claim ↔ source passage" },
  { icon: Network, title: "Claim graph", text: "Inspect connections between claims, assumptions, and cited evidence.", diagram: "Claim → evidence → claim" },
  { icon: ScanText, title: "Peer-review panel", text: "Read three reviewer perspectives and the area chair’s priorities.", diagram: "Methods · claims · evidence → chair" },
  { icon: Eye, title: "Hidden instructions", text: "Flag concealed or instruction-like text for human inspection.", diagram: "Manuscript → text and styling" },
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
      <section id="abstract" data-section="1 · ABSTRACT" className="article-section section-container"><div className="article-section-title" data-enter><span>1</span><h2>Abstract</h2></div><p className="abstract-text" data-enter>A reference can exist without supporting the sentence that cites it. VerRes reads the space between the two: the identity of a source, the passage it contains, and the limits of the claim. <em>Every finding links to its evidence.</em></p></section>
      <section id="how-it-works" data-section="2 · METHODS" className="article-section section-container" aria-labelledby="checks-heading"><div className="article-section-title" data-enter><span>2</span><h2 id="checks-heading">Methods</h2></div><p className="section-intro">Six checks, each with a record you can inspect.</p><div className="methods-grid">{features.map(({ icon: Icon, title, text, diagram }) => <article key={title} data-enter><Icon size={19} strokeWidth={1.4} /><h3>{title}</h3><p>{text}</p><div className="inline-diagram">{diagram}</div></article>)}</div></section>
      <LandingResults />
      <section id="honesty" data-section="4 · LIMITATIONS" className="article-section section-container" aria-labelledby="honesty-heading"><div className="article-section-title" data-enter><span>4</span><h2 id="honesty-heading">Limitations</h2></div><div className="limitations-grid"><div><h3 className="font-serif text-3xl">What we <em>won’t guess.</em></h3><p className="section-intro">A missing source, an abstract without enough detail, or an unverifiable quote leaves a question open. A review is a reading aid; judgment remains with the author.</p></div><article className="honesty-card" data-enter><div><p className="eyebrow">WHEN EVIDENCE IS INSUFFICIENT</p><h3>Needs review</h3><p>We could not retrieve enough source text to verify this claim.</p></div><div><span className="status-pill blue"><CircleAlert size={13} /> NEEDS REVIEW</span><p>Inspect the full paper and cited passage before submission.</p></div></article></div></section>
      <section id="submit" data-section="5 · SUBMIT" className="article-section section-container" aria-labelledby="upload-heading">
        <div className="article-section-title" data-enter><span>5</span><h2 id="upload-heading">Submit</h2></div>
        <div className="upload-grid"><aside className="upload-aside" data-enter><p className="eyebrow">BEFORE THE NEXT SUBMISSION</p><h3>Careful work deserves<br />a careful review.</h3><p>One paper. Citations, claims, a claim graph, an AI peer-review panel, and a scan for hidden prompts.</p><ol><li><span>01</span>Upload a PDF or paste an identifier.</li><li><span>02</span>Follow each check as it happens.</li><li><span>03</span>Open the findings. Inspect the evidence.</li></ol><p className="privacy-note"><LockKeyhole size={13} /> Private. Deleted after 7 days.</p></aside>
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
              SUBMIT
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
      <footer className="journal-colophon section-container"><Brand lockup /><div><p className="eyebrow">VERRES · PRE-SUBMISSION REVIEW</p><p>Every finding links to its evidence.</p><p>Set in Inter, Source Serif 4, and Sora.</p><p>Data sources: Crossref, OpenAlex, arXiv, PubMed, Retraction Watch.</p><a href="#submit">Review your paper <ArrowRight size={13} /></a></div></footer>
    </main>
  );
}
