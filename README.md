# VerRes

Pre-submission integrity review for research papers. Proof, not vibes.
Every finding carries a receipt; insufficient evidence means `NEEDS_REVIEW`.

## Development

Requires Python 3.12 and Docker Compose. The API runs on the host.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
docker compose -f infra/compose.yml up -d grobid db
make run
```

Blank environment values use development defaults: PostgreSQL at
`postgresql://verres@127.0.0.1:5432/verres`, GROBID at `http://127.0.0.1:8070`,
frontend at `http://localhost:3000`. GROBID can take time to initialize.
`curl --fail localhost:8000/health` returns `status: ok` when both dependencies are ready;
otherwise it returns HTTP 503 with `CHECK_INCOMPLETE` and dependency statuses.
Startup applies SQL migrations transactionally and rejects edits to applied migrations.

```sh
make lint
make test
make fmt
make openapi  # writes web/openapi.json, including shared contracts and SSE events
```

Tests use fixtures and mocked HTTP/database clients; no network services are required.
See `contracts/interfaces.py` for async lane interfaces. Callers inject lane implementations
or fixture stubs; business logic and SSE streaming follow in later PRs.

The Compose file is for local development: PostgreSQL uses trust authentication and both
service ports bind only to loopback. `compose.prod.yml` and `Caddyfile` are deployment
scaffolds; production configuration is not implemented in A1.

Partner B's contract-compatible ingestion, resolution, source, verification and graph
implementations are available through `api.app.providers.services.build_backend`.
See the [integration handoff](api/app/verify/PARTNER_B_HANDOFF.md) for dependency injection,
JSONB storage compatibility, scientific evaluation tooling and remaining A3 wiring.
