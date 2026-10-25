# Partner B correctness handoff

## Current integration update

Main `21ecc9c` includes the B/C fixes and 40-candidate preparation, model wiring,
report/evidence/graph/review UI, sharing and deployment support. The historical
A3 wiring limitation below is resolved: `build_services` now injects the primary
model into verification and graph services, and an optional adjudicator into
verification. Missing configuration still produces explicit uncertainty.

The current A11b policy permits distinct same-vendor model IDs by default through
`ADJUDICATOR_ALLOW_SAME_VENDOR`. Same-vendor checks are labeled as such; they do
not meet the original cross-vendor independence requirement. Setting that policy
false preserves abstention until an eligible different-vendor adapter is supplied.

The offline follow-up in `api/app/eval/BAKEOFF.md` prepares blind human review,
artifact-bound export and a fixture-only rehearsal. Human labels and measured
scientific accuracy remain unavailable. Model wiring and a successful live job
do not replace that measurement. The rest of this document records the original
correctness candidate and its historical validation results.

Base: `origin/main` at `03cbc3d` (A1/A2/A3, D1/D2 and three demo papers).
Fix branch: `codex/partner-b-correctness`. Shared contracts, job/orchestrator code,
migrations, infrastructure and frontend source remain unchanged.

## Delivered fixes

- Quote receipts now require exact case-sensitive correspondence after Unicode
  typography/whitespace normalization. No fuzzy edits, negation changes, numeric
  sign changes, cropped numeric tokens or altered scientific-unit capitalization.
  Four-word minimum remains. Judge/adjudicator outputs are limited to three quotes
  by the provider schema, output validation and deterministic gate.
- Full-source severe adjudication requires distinct nonempty configured model IDs,
  families AND vendors. Model identity comes from trusted configuration, never papers.
  `JSONGatewayModel(..., vendor="configured-company")` supplies vendor identity.
  Existing injected adapters without vendor metadata can still give ordinary findings;
  severe findings abstain until independent identity is configured.
- Source PDFs containing raster images, vector paths or rectangles do not qualify
  as FULL_TEXT without OCR/vision coverage. They fall back to a real available abstract,
  otherwise METADATA_ONLY/CHECK_INCOMPLETE. This deliberately includes graphical or
  decorative PDFs: the current extractor cannot certify their whole-source coverage.
  Text-only PDFs still require identity checks and nonempty extracted text on every page.
- Ingest accepts the same 25 MiB limit as intake. Source HTTP downloads retain their
  separate 20 MiB bound. PDFium fallback enforces 80 pages, closes native resources,
  and serializes native PDFium calls across worker threads.
- The fallback is `pypdfium2 + regex`, labeled basic parser and always NEEDS_REVIEW.
  It recovers bracketed/numbered bibliography entries, stable sentence/reference IDs,
  bounded citation ranges, sections and citation context. Duplicate/missing reference
  numbers are not guessed. Author-year references and complete metadata are not inferred.
- OpenAlex/arXiv display names remain intact. Compound surnames can match without
  dropping particles. Unparseable display names cannot establish DOI_MISMATCH.
  Structured surnames are preferred when combining corroborating provider records.
- Dated retraction/correction/concern flags require notice receipts; missing notice
  links yield UNKNOWN. Retraction notices preserve corrections and concerns separately;
  all notices for one DOI survive import. Temporal checks map to existing public enums.
- Claim-map citation IDs must belong to the node's cited sentences. Unrelated
  associations are rejected rather than receiving evidence-based coloring.
- Evaluation reports hash the actual bounded output schema and record configured
  vendor identity. No measured scientific accuracy is claimed by fixture tests.

## Retraction Watch import requirement

An empty table is unavailable data, not an authoritative empty search. Clean results
require an explicitly complete snapshot with an explicit, timezone-aware actual fetch
receipt no older than seven days:

```python
from api.app.resolve.retraction import PostgresRetractions

store = PostgresRetractions(pool)
accepted, rejected = await store.import_csv(
    downloaded_csv,
    complete=True,
    fetched_at=verified_download_time,  # actual retrieval time; do not substitute file mtime
)
```

Complete imports reject malformed/empty/stale inputs before changing stored data.
They atomically replace rows and store a versioned checksum/freshness marker under
`retraction-watch:snapshot:v1` in existing `http_cache` JSONB storage. The marker expires
seven days after fetching. This requires no migration. Imports are serialized by an
advisory transaction lock; lookups read marker and records in one SQL snapshot.

Partial imports revoke completeness. Missing, expired, partial or corrupt snapshots
return `None`/UNKNOWN for checks, including negative lookups. Existing installations
need a new complete import; old rows alone do not prove completeness. Schedule refresh
in Lane A/operations. `RetractionRecord.retracted` stores the notice's effective date,
including correction/concern dates; `notice_type` distinguishes them.

## Public integration remains unchanged

`build_backend(settings, pool=pool, primary=primary, adjudicator=adjudicator)` returns
contract implementations for `Ingest`, `Resolve`, `Sources`, `Verify`, and `Graph`.
The bundle owns its gateway and closes it through its async context manager. Existing
A3 already calls these services. A3's default `build_services` does not configure model
adapters, so Lane A must supply configured primary/adjudicator adapters before live
scientific judgments can run. Missing model configuration yields NEEDS_REVIEW.

No new public fields/statuses or incompatible replacement application models are added.
Internal Work records retain full-name parsing provenance; public adapters stay explicit.
The frozen OpenAPI schema is unchanged by these fixes.

## Contract proposal and remaining integration work

The frozen `Reference` omits work type. Non-arXiv references with no authoritative
coverage information remain CHECK_INCOMPLETE rather than guessing NOT_FOUND or
UNCHECKABLE. Proposed additive field for Lane A approval:

```python
work_type: Literal[
    "journal-article", "proceedings-article", "preprint", "book", "website", "software", "dataset"
] | None = None
```

Affected consumers: Ingest/Resolve/Source adapters, stored Paper/Report payloads,
OpenAPI generation and generated frontend types. No contract change is made here.

Upload admission/storage cleanup, retention, public snapshot IP removal, CORS, model
lifecycle/configuration, report/evidence UI and deployment remain A/D responsibilities.
This branch does not replace their implementation.

The three demo PDFs now exist in `fixtures/pdfs`. Forty independent human labels and
configured live model runs are still missing; `api/app/eval/pairs.jsonl` remains empty.
The tooling does not invent labels, performance numbers or benchmark outcomes.

## Validation of this candidate

- `make lint`: passed, 75 files formatted.
- `make test`: 303 passed (247 on the starting main), one existing Starlette warning.
- `.venv/bin/python -m pip check`: passed.
- Generated `app.openapi()` equals main's committed OpenAPI JSON; contracts are unchanged.
- `npm run build -- --webpack`: passed against the merged D2 frontend, including TypeScript.
  Webpack was used because local Turbopack is restricted from binding its worker port.
- Disposable PostgreSQL 17.11 smoke check: all three migrations and an idempotent rerun,
  complete/partial/invalid/expired snapshots, grouped notices, replacement, and concurrent
  import/read transactions passed. The temporary container was removed afterward.

Unit tests remain offline and fixture-backed. Live GROBID/provider/model behavior and
scientific accuracy were not claimed by these checks.
