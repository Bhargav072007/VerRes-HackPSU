"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
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
  const reduced = useReducedMotion();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState("");
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
    setNotice("");
    setError(message ? { code: "file_invalid", message } : null);
    if (input.current) input.current.value = "";
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setNotice("");
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
    if (result.ok) router.push(`/check/${encodeURIComponent(result.job_id)}`);
    else {
      setError(result.error);
      setBusy(false);
    }
  }

  function trySample() {
    setError(null);
    setNotice(
      "Sample papers will be available soon. Upload a PDF or enter an identifier to start.",
    );
  }

  return (
    <main
      id="main"
      className="mx-auto max-w-6xl px-6 pt-12 pb-12 md:px-10 md:pt-16"
    >
      <section aria-labelledby="headline" className="text-center">
        <p className="mb-5 text-[10px] font-medium tracking-[.2em] text-muted-foreground uppercase">
          A little scrutiny. A stronger paper.
        </p>
        <h1
          id="headline"
          className="font-serif text-[clamp(3rem,7vw,5.5rem)] leading-[1.08] tracking-[-.055em]"
          aria-label="Proof, not vibes."
        >
          {"Proof, not vibes.".split(" ").map((word, i) => (
            <motion.span
              key={word}
              aria-hidden="true"
              data-reveal
              className="inline-block"
              initial={reduced ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={
                reduced
                  ? { duration: 0 }
                  : {
                      ...motionTokens.fade,
                      delay: i * motionTokens.wordStagger,
                    }
              }
            >
              {i > 0 ? "\u00a0" : ""}
              {word}
            </motion.span>
          ))}
        </h1>
        <p className="mx-auto mt-5 max-w-md text-sm leading-6 text-muted-foreground md:max-w-none md:text-base">
          A pre-submission integrity review for research papers.
        </p>
      </section>

      <form
        onSubmit={submit}
        className="mx-auto mt-10 max-w-[650px]"
        aria-label="Submit a paper"
        aria-busy={busy}
      >
        <motion.section
          layoutId="job"
          transition={reduced ? { duration: 0 } : motionTokens.layout}
          className="rounded-xl border bg-white p-5 md:p-6"
        >
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-sm font-medium">
              Give your paper a second look.
            </h2>
            <span className="text-[9px] tracking-[.14em] text-muted-foreground">
              01 / SUBMIT
            </span>
          </div>
          <div
            className="drop-zone relative overflow-hidden rounded-lg border border-dashed"
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
              className="flex w-full flex-col items-center px-4 py-7 disabled:cursor-wait"
            >
              <span className="mb-4 flex size-10 items-center justify-center rounded-lg border bg-background">
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
              setNotice("");
            }}
            placeholder="2401.12345 or 10.1000/xyz"
            className="h-11 w-full rounded-md border bg-white px-3 text-sm placeholder:text-muted-foreground/70 disabled:opacity-60"
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
            className="mt-4 h-11 w-full gap-2 rounded-md text-xs"
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
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          <span className="mr-1 text-[11px] text-muted-foreground">
            Try a sample
          </span>
          {["Clean paper", "Retracted reference", "Planted problems"].map(
            (sample) => (
              <Button
                key={sample}
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={trySample}
                className="h-7 rounded-full bg-transparent px-3 text-[10px] font-normal"
              >
                {sample}
                <ArrowRight className="size-3" />
              </Button>
            ),
          )}
        </div>
        {notice && (
          <p
            role="status"
            className="mt-3 text-center text-xs leading-5 text-muted-foreground"
          >
            {notice}
          </p>
        )}
      </form>

      <section
        id="how-it-works"
        aria-label="How it works"
        className="mt-14 grid gap-6 border-t pt-7 md:grid-cols-3 md:gap-10"
      >
        {features.map(({ icon: Icon, title, text }, i) => (
          <article key={title}>
            <div className="mb-3 flex items-center gap-2 text-muted-foreground">
              <Icon size={16} strokeWidth={1.5} />
              <span className="text-[9px] tracking-widest">0{i + 1}</span>
            </div>
            <h2 className="font-serif text-lg">{title}</h2>
            <p className="mt-2 max-w-xs text-xs leading-5 text-muted-foreground">
              {text}
            </p>
          </article>
        ))}
      </section>
    </main>
  );
}
