# B/C evaluation candidates

Prepared on `codex/bc-evaluation` from B/C correctness commit
`284141fa041516e8b4d22f78584635776e2b6bcd`, then rebased onto main
`0dac983c953a341e3625b60a25f44d2dce3fdf38` after the review panel and report
reader merged. This branch does not modify PR #1 or its branch.

There are **40 distinct sentence–source pairs**, covering **33 source works**:

| Fixture | Candidates | Status |
| --- | ---: | --- |
| paper1_attention.pdf | 30 | Real paper |
| paper2_retracted_reference.pdf | 5 | Synthetic test draft |
| paper3_planted_problems.pdf | 5 | Synthetic test draft |

These are candidates for human review, not a completed accuracy benchmark.
Every `human_label` and `labeled_by` is JSON `null`. `pairs.jsonl` stays empty.
Candidate preparation and validation use no model bakeoff, paid model calls,
credentials or authenticated APIs. Publishing requires separate credential approval.

## Files and evidence

- `candidates.jsonl`: exact citing sentence (PDF extraction with NFC and whitespace
  normalization), PDF page and hash, original bibliography entry and marker,
  source identifier, exact short quote, locator and synthetic flag.
- `sources.jsonl`: authentic source title, public retrieval URL, retrieval time,
  SHA-256 of the fetched artifact, format and evidence coverage. The original
  Transformer fixture is also used as a source for two distinct synthetic claims.
- `proposed_labels.jsonl`: Codex's tentative suggestions and reasons, stored
  separately from human fields. These suggestions are not independent annotations
  or admitted production verdicts. They can be hidden during blind human review.
- `excluded_candidates.jsonl`: a planted citation for which no authentic source
  was verified; excluded from the 40 rather than supplied with invented evidence.

Each quote's role is explicit: supporting context, limiting context or method
attribution. A quote may support only one component of a multi-source sentence.
Limiting context is evidence to inspect for a possible overstatement, not proof
that the entire source lacks a claim. Method citations describe an attributed
technique; they cannot independently establish the citing authors' own settings.

Most sources are public abstracts, explicitly `ABSTRACT_ONLY`. Four source works
have full PDFs available, marked `FULL_TEXT` in the receipt. Availability of a full
PDF does not mean an independent whole-source adjudication has happened. Severe
production verdicts still require all existing evidence gates. Quotes from the
retracted Wakefield paper document its historical wording only; its receipt
records the retraction warning and notice DOI.

Downloaded artifacts are cached locally under ignored `data/evaluation_sources/`.
Only short quotes and provenance are committed. The PDFs supplied in
`fixtures/pdfs/` are unchanged. Printed hyphens and formula extraction artifacts
are retained; column extraction is used for source PDFs where needed.

## Validate

From the repository root:

```sh
.venv/bin/python -m api.app.eval.candidates
```

This offline command checks count and paper coverage; null human fields; synthetic
markings; unique IDs and normalized sentence–source fingerprints; proposal
coverage; citing sentences, reference entries and PDF hashes; source artifact
hashes; and exact quotes on recorded source PDF pages. Quotes must contain at
least four words. Different markers in the same sentence do not create another
pair for the same source. DOI case, DOI URL aliases and arXiv versions normalize
to the same source identity. Separate sentences citing the same source are valid
distinct pairs. This does not automatically detect paraphrases or cross-registry
aliases; those still need human review.

On a fresh checkout, explicitly fetch public evidence first:

```sh
.venv/bin/python -m api.app.eval.candidates --fetch
```

The fetcher uses the existing rate-limited Gateway and anonymous public URLs.
It never loads application Settings, credentials or models. Fetched artifacts must
match the pinned receipts. Public HTML/XML may change; a mismatch fails validation
and never silently overwrites a receipt. Review the changed artifact and its quote
before deliberately updating its hash and retrieval time. A missing cache is a
validation failure, not evidence that the quote was verified.

```sh
.venv/bin/python -m api.app.eval.candidates --structure-only
```

This last command checks structure only and explicitly reports
`evidence_checked: false`. Offline unit tests use deterministic local evidence;
they do not claim to re-download or authenticate the public corpus in CI.

## Human review next

Read the original citing PDF and source, verify source identity and scope, and
assign a label with an annotator name in a separately reviewed dataset version.
Split compound claims during that review if needed, preserving the original pair
identity and avoiding duplicate counting. Keep synthetic provenance. Convert
approved records to `EvalPair` only with correctly represented source coverage;
never promote a short quote to a full-text source or copy proposed labels into
human fields. Ask the user before any credential use, push requiring credentials,
or paid model evaluation.
