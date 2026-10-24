# Partner B integration handoff

Branch: `codex/partner-b-backend`. Integrated upstream `fc9e48e`, containing A1 shared
contracts, A2 jobs/SSE and D1 frontend. Published branch history is retained with a merge;
no force push or merge of PR #2 is required.

## Public interfaces

`contracts/schema.py` and `contracts/interfaces.py` are unchanged. These concrete classes
implement the exact async protocols and return the shared Pydantic models:

| Protocol | Implementation | Methods and return types |
|---|---|---|
| `Ingest` | `api.app.ingest.service.IngestService` | `parse_pdf(data) -> Paper`; `scan_hidden_text(data) -> list[HiddenTextFinding]` |
| `Resolve` | `api.app.resolve.service.ResolveService` | `resolve_reference(reference) -> ExistenceResult`; `check_retraction(existence, paper_date) -> RetractionResult` |
| `Sources` | `api.app.sources.service.SourceService` | `fetch_source(existence) -> SourceDocument` |
| `Verify` | `api.app.verify.service.VerifyService` | `verify_citation(citation, source) -> SupportResult` |
| `Graph` | `api.app.graph.service.GraphService` | `build_claim_map(paper) -> ClaimMap` |

The public boundary uses shared names and enums: `VERIFIED` (not `FOUND`),
`ABSTRACT_ONLY`/`METADATA_ONLY`, `RetractionStatus.NONE`/`UNKNOWN`, and evidence strength
`INSUFFICIENT`. `NEEDS_REVIEW` support always includes `needs_review_reason`. Definitive
support always includes verified source receipts, and severe labels set `adjudicated`
only after agreement by different model IDs and families.

`ParsedPaper`, `ParsedReference`, `ParsedCitation`, `ParsedSentence`, `Work`, atomic-claim
types and other internal processing records retain extraction/provider details. They
are not application/API contracts. The public adapters perform explicit conversions;
they never serialize private models into jobs or SSE. The judge uses `contracts.schema.Judgment`
directly, and graph extraction uses `contracts.schema.ClaimMap` directly.

## Integration and lifecycle

```python
from api.app.providers.services import build_backend
from api.app.settings import Settings

# Lane A supplies its pool and configured Model adapters; no model name/key is guessed.
async with build_backend(Settings(), pool=pool, primary=primary,
                         adjudicator=adjudicator) as backend:
    paper = await backend.ingest.parse_pdf(pdf_bytes)
    hidden = await backend.ingest.scan_hidden_text(pdf_bytes)
    existence = await backend.resolve.resolve_reference(paper.references[0])
    retraction = await backend.resolve.check_retraction(existence, paper.paper_date)
    source = await backend.sources.fetch_source(existence)
    support = await backend.verify.verify_citation(paper.citations[0], source)
    claim_map = await backend.graph.build_claim_map(paper)
```

The bundle owns/closes its gateway. Inject a gateway via `gateway=...` when supplying
extra configured HTTPS model providers or deterministic transports. Model adapters sharing
that gateway must use it within the bundle's lifetime. `openalex_daily_budget_usd` configures
the OpenAlex guard separately from Lane A's `llm_daily_budget`. Missing Crossref identity
or model configuration produces explicit incomplete/review outcomes.

The A2 `get_client(provider)` hook remains available with its shared-per-provider lifecycle,
20-second read and 5-second connect timeouts. Existing main/health/lifespan behavior is
preserved. Source downloads use the stricter gateway `safe_fetch`, not this compatibility
hook. Lane A still owns job routes, SSE, persistence and the future A3 orchestrator; none
of those modules, shared contracts, migrations, workflows or frontend files are changed
relative to upstream. These services are injectable implementations, not a replacement
job API or an implicit production orchestration change.

## Storage compatibility

Adapters target the actual A1 tables from `infra/migrations/001_init.sql`; no new columns
or migrations are required:

- `http_cache(cache_key, payload, expires_at)`: JSONB payload contains HTTP status,
  base64-encoded body and headers. Invalid/incompatible cached payloads are misses.
- `retraction_watch(doi, payload, updated_at)`: JSONB contains normalized DOI, nullable
  retraction date, provenance and optional notice URL. CSV import preserves notice DOI
  receipts and skips known non-retraction notices. Missing/invalid rows or unavailable
  snapshots are not treated as evidence of non-retraction.

`PostgresRetractions.lookup` returns `None` on unavailable/corrupt storage. Pass a complete,
current RW snapshot to the resolver before relying on a clean chronological check. OpenAlex
`is_retracted=True` without a dated notice remains `UNKNOWN`; a retraction is flagged as
pre-existing only when it predates the citing paper.

## Evidence and schema compatibility

`VerifyService` retains the supplied `SourcePassage.passage_id` through BM25 retrieval,
quote checks and full-source adjudication. It rejects mismatched reference IDs, duplicate
passage IDs, empty source passages and missing citation sentence IDs. It never regenerates
passage IDs at the public boundary. Quotes require at least four words and normalized
fuzzy similarity of 0.95, with numbers and negation protected. Abstract-only evidence
cannot produce severe labels; full support requires DIRECT evidence.

Judge/adjudicator prompt version v2 uses shared enum names and shared Judgment schema.
Historical v1 files remain available. The provider adapter renders defaults as explicit
required properties for strict JSON output without mutating the shared schemas. Graph
v1 uses shared node kinds/edges; invalid IDs, oversized nodes, duplicates and cycles are
removed with a review reason. Graph extraction does not invent source receipts or
evidence-based node status fields absent from the frozen contract.

Source fetching retains HTTPS/public-DNS/redirect checks, pinned connections with original
Host/TLS SNI, decoded-body limit of 20 MB, a 20-second network deadline, and arXiv throttling.
Full-text identity is checked against available title/author metadata; failed/scanned
extraction falls back to an abstract or explicit unavailable result. PDF extraction has
no OCR or figure interpretation. Worker resource isolation remains a deployment concern.

The shared `Reference` has no venue, work-type or PMID fields. Available raw reference text
is preserved; additional extraction details remain internal. Without authoritative work
type, an unrecognized record stays `CHECK_INCOMPLETE` rather than inferring index coverage
from a DOI. arXiv IDs supply preprint coverage. A future optional work-type/venue extension
can improve coverage, but this branch does not change contracts to obtain it.

## Development and validation

The merged root `pyproject.toml` is the sole dependency source. Existing A1/A2 pins are
retained; parser, limiter, YAML/fuzzy matching and PDF test dependencies are added there.
The incompatible bootstrap lock file is removed. Upstream Makefile commands are retained,
and pytest collects both `tests/` and `api/tests/`:

```sh
.venv/bin/python -m pip install -e '.[dev]'
make lint
make test
make openapi
.venv/bin/python -m pip check
```

Tests include the unchanged A1/A2 contract, health, database, upload/jobs and SSE suites,
the original Partner B logic tests, and public-interface regressions. A deterministic
integration test parses PDF/TEI, resolves metadata, acquires source PDF, verifies a citation,
and round-trips every resulting public object through Report and the A2 SSE union. HTTP,
model, PDF and database transports use explicit synthetic fixtures; no live network or
scientific quality is claimed by these tests.

## Evaluation and remaining work

`api/app/eval/pairs.jsonl` remains empty because the three actual demo papers and 40 human
labels have not been supplied. `EvalPair.model_json_schema()` gives the labeling format;
`python -m api.app.eval.bakeoff ...` manages labels, and `run_bakeoff` compares configured
models. Reports include actual judge v2/schema hashes, dataset hash/version, model identity,
UTC time, raw/admitted accuracy, severe false positives, service/JSON errors and quote
failures. An abstention without a quote is not itself a fabricated-quote failure.

Real GROBID/PostgreSQL/provider/model integration and the scientific bake-off still require
configured services/data. A3 orchestration and model-run persistence remain Lane A work.
No C7 requirement was supplied. The OpenAlex guard uses reported `meta.cost_usd` per process,
allows cached records after its limit, and closes new paid requests when cost metadata is
unknown. It is not a distributed reservation system or a hard pre-request spending cap.
