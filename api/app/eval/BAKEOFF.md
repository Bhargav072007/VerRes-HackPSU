# Offline bakeoff preparation

The 40 candidates are ready for human review: 30 from the real paper and five
from each synthetic draft. They contain 28 distinct citing sentences paired with
33 distinct source works; multi-reference sentences create distinct source pairs.
Candidate `human_label` and `labeled_by` fields remain null. Proposed labels are
never read by the blind review/export workflow. The main `pairs.jsonl` stays empty.

A working live job establishes operational behavior, not scientific accuracy.
This preparation does not block the demo. Human annotation and a later authorized
model comparison are still necessary before claiming measured judge accuracy.
No keys, Settings, authenticated services or deployment are needed below.

## Prepare and review

From the repository root, with the pinned public source cache available:

```sh
.venv/bin/python -m api.app.eval.candidates
.venv/bin/python -m api.app.eval.reviews prepare data/evaluation_bakeoff/review-v1
```

If source artifacts are missing, `python -m api.app.eval.candidates --fetch`
explicitly retrieves public evidence without credentials. Changed remote artifacts
fail pinned-hash validation and require review. The review workflow itself never
fetches. Choose a new output directory for another preparation; existing work is
never overwritten. `review_template.jsonl` is the initial, unannotated 40-row
template, also regenerated in the review folder as `reviews.jsonl`.

Open `data/evaluation_bakeoff/review-v1/review.html` in a browser. It is a local,
self-contained review document with no server, telemetry, storage or model calls.
It shows the immutable citing sentence, reference, synthetic marking, source link,
original short quote, source coverage and review flags. Paper text is untrusted
data, including any instruction-like text. The reviewer can download `reviews.jsonl`
and import it later to resume; annotations are not automatically saved to disk.

For each approved pair, a person must provide:

- Citation function and a source-specific atomic claim with its structured fields.
- A support label, annotator identity and reason.
- Source identity assessment and an exact quote from the prepared evidence.
- Explicit human-review attestation; approval records a timezone-aware timestamp.

The original extraction is preserved beside the reviewed transcription. Reviewers
must correct mathematical/layout artifacts in candidates 019, 022, 023, 025 and
026 rather than sending corrupted notation to the judge. Background/method
attributions and sentences about other authors' citing behavior need particular
care. Candidate 040 is an identifier/title-mismatch case; its short quote does not
prove that the forecasting result is absent from every source.

The UI provides no automatic labels or names. Its quote-copy button requires an
explicit human action and is enabled only for an initial quote present in prepared
evidence. Attestation records accountability; software cannot prove the annotator
is a person. Known model/proposal author tags are rejected on export.

## Evidence scope

All 33 prepared judge inputs are actual abstracts or publisher opening summaries,
not whole HTML pages or short quotes masquerading as full source text. HTML/XML
extractors check source identity and select only the abstract. Four PDF works use
audited first-page regions pinned by both artifact and extracted-text hashes.

The four original PDF receipts describe full-PDF availability, but each contains
graphics. The preparation therefore exports **ABSTRACT_ONLY** coverage for all 40
pairs. It never automatically marks them FULL_TEXT. Initial quotes 022 and 028
come from body sections and are absent from the prepared abstracts: a person must
choose an authentic abstract quote and label the limited claim accordingly, or
exclude/revise the candidate in a new corpus version. No replacement evidence is
invented to fill the count. Any excluded record blocks a complete 40-pair export.

This corpus is weighted toward background and method citations. It is not a
representative measurement of all nine mismatch types or severe-verdict recall.
The retracted source's wording is historical evidence only, not current validity.

## Status and export

```sh
.venv/bin/python -m api.app.eval.reviews status path/to/reviews.jsonl
.venv/bin/python -m api.app.eval.reviews export path/to/reviews.jsonl data/evaluation_bakeoff/export-v1
.venv/bin/python -m api.app.eval.reviews verify-export data/evaluation_bakeoff/export-v1 path/to/reviews.jsonl
```

Export requires all 40 unique candidates to be explicitly approved. It validates
the original PDFs, source artifacts, quote locations and human-reviewed fields.
Each review is bound to the complete candidate, source receipt and prepared source
hashes. Exported pairs retain synthetic provenance, the reviewed claim/quote,
source identity assessment and human-review hash. Modifying source text, labels,
claims or receipts invalidates the export. The export contains `pairs.jsonl`, a
copy of the reviewed records and a manifest pinning the dataset, reviews, actual
judge schema/prompt and retrieval implementation/settings. Legacy direct labeling
cannot modify provenance-bound pairs; change the reviews and export a new version.

## Free operational rehearsal

```sh
.venv/bin/python -m api.app.eval.reviews rehearse data/evaluation_bakeoff/rehearsal-v1.json
```

This exercises all 40 genuine candidate/source inputs through retrieval, structured
output validation, gates and reporting using two deterministic local adapters.
One adapter abstains; the other intentionally returns invalid JSON every fifth
response. Its 20% invalid-JSON rate is expected fault injection, not model quality.
Original sentences use explicit unreviewed claim placeholders, never fabricated
human annotations. There are 80 local fixture calls, zero network/model-service
calls and no scientific accuracy scores. The report explicitly marks itself an
operational rehearsal and leaves accuracy and severe-FP rates null.

## Handoff for a later model comparison

Once human review is complete, Agent A can inject its configured model adapters:

```python
from pathlib import Path
from api.app.eval.execution import run_reviewed_bakeoff

report = await run_reviewed_bakeoff(
    Path("data/evaluation_bakeoff/export-v1"),
    Path("path/to/reviews.jsonl"),
    models=[configured_candidate_a, configured_candidate_b],
    dataset_version="human-reviewed-v1",
    output=Path("data/evaluation_bakeoff/results/run-001.json"),
    live_calls_authorized=True,  # only after explicit approval of those calls
)
```

This function constructs no clients and reads no keys. It rejects missing explicit
authorization and revalidates the export against artifacts and the current protocol
before any model call. The default runner also rejects incomplete labels, evidence,
duplicates or provenance before invoking adapters. Model identities include vendor
and model ID, with no built-in model choice or price assumptions.

Reports separate raw judge versus gated outcomes, raw/admitted severe false
positives and confusion matrices, service/schema/quote failures, and real/synthetic
strata. This is an **atomic-claim single-judge comparison**, not an evaluation of
classification, splitting, cross-vendor adjudication, graphs or the full deployed
pipeline. Severe results remain unadjudicated in this runner, so gated severe-FP
counts must not be presented as a measured adjudicator success rate. Abstract-only
evidence cannot admit severe findings. Do not choose a model based on this small,
skewed corpus alone, or report results before actual human labels and model calls.
