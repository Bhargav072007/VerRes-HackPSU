# Partner B implementation and integration handoff

Base: `5243e4789a1b4bee2b3502a7d5d74bfd9e33c45b` (README and license only).
Branch: `codex/partner-b-backend`.

The user approved provisional Partner B models because Lane A contracts are absent.
No `contracts/`, HTTP routes, jobs, SSE, migrations, deployment, or frontend are implemented
here. These modules expose Python interfaces for the integrator. Shared contract
compatibility remains **unverified until Lane A supplies its schemas**. Do not treat the
provisional statuses as an agreed public API. No C7 requirement was supplied.

## Development

From the repository root, with Python 3.12:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r api/requirements-partner-b.lock.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q
.venv/bin/ruff check api
.venv/bin/ruff format --check api
```

The lock file records the installed environment used for validation. Runtime and test
dependency ranges are in `pyproject.toml`. All tests block real sockets and DNS. HTTP/model
fixtures are synthetic, explicitly not recorded demo papers, human ground truth, or live
provider validation. A single offline integration test composes real TEI parsing,
metadata resolution, source PDF extraction, retrieval, and quote-validated verification.

## Scope and dependency order

| Deliverable | Implementation | Dependencies and acceptance |
|---|---|---|
| B1 | `ingest/tei.py`, `ingest/pdf.py` | Safe TEI parsing, stable sentence IDs, bibliography pointers and neighboring sentences; GROBID configured at 60 seconds. Malformed/partial data yields structured results. |
| B2 | `providers/http.py`, `cache.py`, `metadata.py`, `providers.yaml` | Reused async clients, rate/concurrency limits, bounded jitter retries, Retry-After, circuit breakers, TTL caching, Crossref/OpenAlex/arXiv clients. |
| B3 | `resolve/existence.py` | B1+B2: identifier agreement; weighted title/author/year/venue search with score/margin gates; uncertainty on outages/unknown coverage. Corroborating provider metadata retains OA access and abstract provenance. |
| B4 | `resolve/retraction.py` | B2+Lane A table: Retraction Watch CSV import adapter and date-aware OpenAlex/RW checks. Known correction/concern records are excluded. Missing dates/sources are incomplete. |
| B5 | `resolve/doi.py` | B3: separate invalid syntax, unresolved DOI, mismatch, disagreement, and incomplete metadata. |
| B6 | `ingest/pdf.py` | PDF fixtures: white/near-white fill, tiny font, render mode 3, off-page characters, instruction patterns; findings describe suspicious artifacts, never intent. Coordinates are page-relative top-left. |
| B7 | `ingest/pdf.py` | B1: PDF fallback recovers text with partial status and no invented references or links. |
| C1 | `eval/bakeoff.py`, `eval/pairs.jsonl` | Scaffolding ready; real completion requires 40 human-labeled pairs from 3 supplied papers and configured model runs. Empty dataset deliberately shipped. |
| C2 | `sources/acquire.py` | B2: OA PDF, then arXiv PDF, then Crossref JATS/OpenAlex index abstract. Rejects unverifiable PDF identity or blank/scanned pages. |
| C3 | `verify/model.py`, `models.py`, `retrieval.py`, `pipeline.py`, `prompts/` | C2: batches of 10, 1-3 atomic claims, ~200-word BM25 chunks/top 8 plus abstract, strict versioned JSON prompts. |
| C4 | `verify/gates.py` | C3: normalized quote matching at 0.95, protecting numbers/negation, passage IDs, evidence-level restrictions, explicit review reasons and worst-case aggregation. |
| C5 | `verify/pipeline.py` | C4: severe full-text findings require different model IDs/families, unanchored whole-source read, matching labels and independently verified evidence. Context overflow returns uncertainty. |
| C6 | `graph/build.py` | B1: at most 12 short nodes with valid supplied sentence IDs; invalid/duplicate/cyclic relationships dropped. Citation results color nodes after verification. |

This bootstrap is one review candidate with logical commits, since none of the foundation
contracts or application structure existed. It exceeds the playbook's suggested small-PR
size. Future changes should be split by the deliverables above after the interfaces freeze.

## Python interfaces (all provisional)

```python
parse_tei(data: bytes) -> ParseResult
await ingest_pdf(data: bytes, gateway: Gateway) -> ParseResult
fallback_pdf(data: bytes) -> ParseResult
scan_hidden_text(data: bytes) -> HiddenScan
await resolve_reference(ref: Reference, crossref, openalex, arxiv=None) -> ExistenceResult
await check_doi(reference: Reference, crossref, openalex) -> DOICheck
check_retraction(work: Work, citing_date: date | None,
                 records: list[RetractionRecord] | None) -> RetractionResult
await acquire_source(work: Work, gateway: Gateway, crossref_work=None) -> Source
await classify_citations(citations: list[Citation], model: Model) -> dict[str, str]
await verify_citation(citation: Citation, source: Source, primary: Model,
                       adjudicator=None, citation_function=None) -> CitationVerification
await build_graph(paper: Paper, model: Model) -> ClaimGraph
color_graph(graph: ClaimGraph, paper: Paper,
             results: list[CitationVerification]) -> ClaimGraph
await run_bakeoff(pairs: list[EvalPair], models: list[Model],
                   dataset_version: str, output: Path | None = None) -> dict
```

Keyword-only parameters remain keyword-only in actual code. `Record` uses strict
Pydantic validation and forbids extra fields. Paper models live in `ingest/models.py`,
metadata in `providers/models.py`, resolution models beside their functions, Source
in `sources/acquire.py`, verification in `verify/models.py`, graph in `graph/build.py`.
There are no numeric verdict confidence fields. Matching scores are internal heuristics.

## Gateway and model configuration

```python
import os
from app.providers.http import Gateway, Policy, load_policies
from app.providers.cache import PostgresCache
from app.providers.metadata import Crossref, OpenAlex, Arxiv

policies = load_policies()
# GROBID is a trusted configured service, not a URL taken from a document.
policies["grobid"] = Policy(os.environ["GROBID_URL"], rate=1, period=1, concurrency=1)
async with Gateway(policies, cache=PostgresCache(pool)) as gateway:
    crossref = Crossref(gateway, mailto=os.environ["CROSSREF_MAILTO"])
    openalex = OpenAlex(gateway, api_key=os.environ.get("OPENALEX_API_KEY"))
    arxiv = Arxiv(gateway)
    # Integrator calls module functions here, then persists/emits results in Lane A.
```

`Model` is a small provider-neutral protocol with `model_id`, `family`, and async
`complete(task, system, data, schema) -> str`. `JSONGatewayModel` implements a configured
chat-completions-compatible strict-JSON endpoint through this gateway. Configure an HTTPS
provider policy, model identity, actual family, API key and conservative character context
limit explicitly. Other API protocols need a `Model` adapter. Nothing chooses model names,
invents credentials, or silently truncates a source. System prompts are separate from
entity-escaped, nonce-delimited untrusted document data. Record these inputs/outputs and
model IDs in Lane A's model-run storage; this change does not own that storage.

The OpenAlex budget guard reads `meta.cost_usd`; missing/invalid cost closes further paid
requests until the next UTC day. Cached responses remain available without a new charge.
This is a per-Gateway/per-process guard on reported costs, not a multi-worker hard spending
cap; one completed request can cross the configured threshold. Lane A should provide
shared accounting if multiple worker processes or hard cost reservations are required.

Use `Gateway.safe_fetch` for source URLs only: HTTPS, no URL credentials or alternate
ports, all DNS answers must be global, actual connection to a validated IP with original
TLS SNI/Host, connection close to avoid cross-host TLS pool reuse, every redirect rechecked,
20 MB decoded-body bound and 20-second overall network deadline. arXiv PDFs use arXiv's
rate limiter. Provider methods use configured origins and do not follow arbitrary redirects.
Cancellation propagates and releases slots; the gateway context manager closes clients.

`MemoryCache` is ephemeral development storage. For production supply `PostgresCache`.
Cache/database availability errors should not be interpreted as a missing citation.

## Lane A database proposals (not applied migrations)

The adapters expect the following minimal schema. Lane A must review/adapt or create it:

```sql
CREATE TABLE http_cache (
  cache_key text PRIMARY KEY,
  status integer NOT NULL,
  body bytea NOT NULL,
  headers jsonb NOT NULL,
  expires_at timestamptz NOT NULL
);
CREATE INDEX ON http_cache(expires_at);
CREATE TABLE retraction_watch (
  doi text PRIMARY KEY,
  retracted_at date,
  provenance text NOT NULL
);
```

Use `await PostgresRetractions(pool).import_csv(csv_text)` to import the local snapshot;
retain its source date/version externally and check rejected-row counts. Only pass an empty
record list as a definitive lookup when the snapshot is known complete and current. Pass
`None` when the RW source is unavailable. Missing/ambiguous citing or retraction dates remain
incomplete. `is_retracted=True` without a dated RW record cannot establish chronology.
Database adapters have fake-pool tests; a real PostgreSQL service was not supplied.

## Human evaluation

`pairs.jsonl` is empty because no demo papers or human labels were provided. Prepare one
`EvalPair` JSON object per selected citation/atomic claim with `id`, `paper_id`,
`citation_text`, `claim`, `source`, and initially null `human_label`, `labeled_by`,
`label_reason`. Obtain the exact format with `EvalPair.model_json_schema()`.
Select 40 pairs across the actual three demo papers; do not relabel synthetic test examples
as demo ground truth. A human can inspect the input and label each row using:

```sh
PYTHONPATH=api .venv/bin/python -m app.eval.bakeoff api/app/eval/pairs.jsonl
PYTHONPATH=api .venv/bin/python -m app.eval.bakeoff api/app/eval/pairs.jsonl \
  --label-id PAIR_ID --label SUPPORTED --annotator YOUR_NAME --reason 'Evidence explanation'
```

Call `await run_bakeoff(pairs, [candidate1, candidate2], dataset_version=..., output=...)`
with real configured Model adapters after labeling. It records source-dataset/prompt hashes,
model IDs/families, UTC timestamp, predictions and measured metrics. `dataset_ready` is
true only for 40 human-labeled rows from exactly 3 papers. `accuracy` measures raw judge
labels against human labels, counting failed calls as incorrect; `admitted_accuracy` uses
the deterministic gate (severe proposals remain review pending adjudication). Severe false
positives count severe raw labels against non-severe human labels. Invalid structured-output
and service-failure rates use all calls; quote-failure rate uses schema-valid outputs.
Missing denominators are null, not invented zeroes. No scientific accuracy has been measured.

## Review and remaining integration

Offline tests and Ruff are the validation available in this checkout. No independent
review agent, real GROBID, PostgreSQL, scientific-provider calls, production orchestration,
or model bake-off is represented as having run. Human cross-review is still required.

Before production: freeze/map Lane A contracts and statuses; connect storage/orchestration;
configure GROBID/provider identities and model adapters; import and version RW data; supply
the three demo PDFs; label and run the scientific evaluation. PDF extraction lacks OCR and
figure interpretation, and metadata title/author matching is a conservative heuristic.
Hostile PDF resource isolation belongs in the ingestion worker boundary before deploying
untrusted uploads. Fallback parsing deliberately cannot produce reliable citation links.
