import type { paths } from "./api-types";

export type ApiError = { code: string; message: string };
// A2 exports these shapes after its merge; keep the interim contract here only.
export type JobInput =
  { file: File; identifier?: never } | { identifier: string; file?: never };
export type JobResult =
  { ok: true; job_id: string } | { ok: false; error: ApiError };
type Health =
  paths["/health"]["get"]["responses"][200]["content"]["application/json"];
const baseUrl = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

export function validatePdf(
  file: Pick<File, "name" | "type" | "size">,
): string | null {
  if (
    !/\.pdf$/i.test(file.name) ||
    (file.type && file.type !== "application/pdf")
  )
    return "Please choose a PDF file.";
  if (file.size === 0) return "This PDF is empty. Please choose another file.";
  if (file.size > 25 * 1024 * 1024)
    return "This PDF exceeds 25MB. Please choose a smaller file.";
  return null;
}

export function parseIdentifier(
  value: string,
): { doi: string } | { arxiv_id: string } | null {
  const text = value.trim();
  if (text.startsWith("10.") && !/\s/.test(text)) return { doi: text };
  if (
    /^(?:arxiv:)?(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v[1-9]\d*)?$/i.test(
      text,
    )
  )
    return { arxiv_id: text.replace(/^arxiv:/i, "") };
  return null;
}

export async function createJob(input: JobInput): Promise<JobResult> {
  let body: FormData | string;
  if (input.file) {
    const error = validatePdf(input.file);
    if (error)
      return { ok: false, error: { code: "pdf_invalid", message: error } };
    body = new FormData();
    body.append("file", input.file);
  } else {
    const identifier = parseIdentifier(input.identifier);
    if (!identifier)
      return {
        ok: false,
        error: {
          code: "identifier_invalid",
          message: "Enter an arXiv ID or DOI",
        },
      };
    body = JSON.stringify(identifier);
  }
  try {
    const response = await fetch(`${baseUrl}/jobs`, {
      method: "POST",
      body,
      headers:
        typeof body === "string"
          ? { "Content-Type": "application/json" }
          : undefined,
      signal: AbortSignal.timeout(30_000),
    });
    const data: unknown = await response.json().catch(() => null);
    if (
      response.status === 202 &&
      data &&
      typeof data === "object" &&
      "job_id" in data &&
      typeof data.job_id === "string" &&
      data.job_id.trim()
    )
      return { ok: true, job_id: data.job_id };
    if (response.status === 404)
      return {
        ok: false,
        error: {
          code: "NOT_READY",
          message:
            "Paper submission isn’t available yet. Please try again shortly.",
        },
      };
    if (
      data &&
      typeof data === "object" &&
      "code" in data &&
      typeof data.code === "string" &&
      "message" in data &&
      typeof data.message === "string"
    )
      return { ok: false, error: { code: data.code, message: data.message } };
    return {
      ok: false,
      error: {
        code: "CHECK_INCOMPLETE",
        message: "We couldn’t start your review. Please try again shortly.",
      },
    };
  } catch {
    return {
      ok: false,
      error: {
        code: "UNAVAILABLE",
        message:
          "We couldn’t reach the review service. Please try again shortly.",
      },
    };
  }
}

export async function getHealth(): Promise<Health> {
  try {
    const response = await fetch(`${baseUrl}/health`, {
      signal: AbortSignal.timeout(5000),
    });
    const data: unknown = await response.json();
    if (
      data &&
      typeof data === "object" &&
      "status" in data &&
      "db" in data &&
      "grobid" in data &&
      [data.status, data.db, data.grobid].every(
        (value) => value === "ok" || value === "CHECK_INCOMPLETE",
      )
    )
      return data as Health;
  } catch {
    /* External failures are an incomplete check. */
  }
  return {
    status: "CHECK_INCOMPLETE",
    db: "CHECK_INCOMPLETE",
    grobid: "CHECK_INCOMPLETE",
    reason: "The review service is unavailable.",
  };
}
