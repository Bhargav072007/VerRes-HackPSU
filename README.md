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

The development Compose file uses PostgreSQL trust authentication and binds service ports
only to loopback. Use the separate production stack below on the VM.

## Deploy

Run these commands **on the Ubuntu 24.04 VM** (2 vCPU / 8 GB) at `184.197.196.202`.
Allow inbound TCP 80 and 443 in the EC2 security group; keep SSH restricted to your IP.
`184-197-196-202.sslip.io` must resolve to this VM for Caddy to issue its HTTPS certificate.
Only Caddy publishes ports; PostgreSQL, GROBID and the API stay on the Compose network.

Install Docker Engine and Compose using Docker's
[Ubuntu repository instructions](https://docs.docker.com/engine/install/ubuntu/):

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl git nano openssl python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in so Docker group membership takes effect, then prepare the checkout
after A4 is merged into `main` (authenticate Git first if the repository requires it):

```sh
git clone https://github.com/Bhargav072007/VerRes-HackPSU.git ~/verres
cd ~/verres
git checkout main
umask 077
cp .env.example .env
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path('.env')
lines = path.read_text().splitlines()
lines = ['POSTGRES_PASSWORD=' + secrets.token_hex(32) if line.startswith('POSTGRES_PASSWORD=')
         else line for line in lines]
path.write_text('\n'.join(lines) + '\n')
PY
nano .env
```

Keep `API_DOMAIN=184-197-196-202.sslip.io`; fill in provider keys and `FRONTEND_ORIGIN`
for your frontend. The committed password is a public placeholder; the command above
replaces it with a fresh random hex password without printing it. Production Compose sets
`ENV=production`, `GROBID_URL=http://grobid:8070`, `DATA_DIR=/data`, and
`DATABASE_URL=postgresql://verres:${POSTGRES_PASSWORD}@db:5432/verres`, overriding development
values from `.env`. Use a hex password so it is safe in the database URL.

```sh
docker compose --env-file .env -f infra/compose.prod.yml config --quiet
./infra/deploy.sh
curl --fail --show-error https://184-197-196-202.sslip.io/health
```

For subsequent deployments, run `cd ~/verres && ./infra/deploy.sh`. It pulls the current
branch with `--ff-only`, builds and starts the stack, waits up to ten minutes for HTTPS
health (including GROBID initialization), then prints the last 50 API log lines. Failure
returns a nonzero exit status and also prints those lines. Diagnose other services with
`docker compose --env-file .env -f infra/compose.prod.yml logs --tail 50 grobid caddy db`.

Named volumes retain uploaded data, PostgreSQL data, and Caddy certificates across rebuilds
and VM reboots. Startup applies migrations automatically. The PostgreSQL password is set
when its volume is first initialized; changing `.env` alone does not rotate an existing
database password. Back up data before deployments and keep `.env` on the VM only.

Partner B's contract-compatible ingestion, resolution, source, verification and graph
implementations are available through `api.app.providers.services.build_backend`.
See the [integration handoff](api/app/verify/PARTNER_B_HANDOFF.md) for dependency injection,
JSONB storage compatibility, scientific evaluation tooling and remaining A3 wiring.

## Demo day

Run these tools from this checkout with the development dependencies installed.
They print JSON summaries and exit nonzero on request failures or incomplete jobs.
`NEEDS_REVIEW` is a completed review outcome, not a transport failure.

```sh
.venv/bin/python scripts/warm_demo.py https://184-197-196-202.sslip.io
cat demo.json
curl --fail-with-body https://184-197-196-202.sslip.io/status
```

The warmer uploads all three PDFs, waits for each SSE `done`, prints stage timings
and final verdict counts, and saves `{paper: {job_id, report_url}}` to `demo.json`.
Report URLs point to API snapshots. The first run performs real checks; subsequent
runs reuse completed results at the same `PIPELINE_VERSION`, with a new job ID and
the original receipts replayed immediately. `--fresh` (or `POST /jobs?fresh=1`)
bypasses the result cache. Bump `api/app/version.py:PIPELINE_VERSION` whenever a
pipeline change should invalidate saved results.
Jobs containing `CHECK_INCOMPLETE` events are not reused. Stage timings printed
by the scripts measure SSE arrival intervals, so cached and
recorded replays measure replay time; real execution timings are in the API JSON logs.

To prepare recorded demos, keep `DEMO_FIXTURE=0` and `STUBS` disabled, run the
warmer, then record each real job ID from `demo.json`:

```sh
.venv/bin/python scripts/record_fixture.py JOB_ID --base-url https://184-197-196-202.sslip.io
```

The recorder matches the uploaded PDF digest and writes `fixtures/demo/paper1.jsonl`,
`paper2.jsonl`, or `paper3.jsonl`. It requires an ordered journal ending in `done`,
rejects fixture/stub output, and preserves the receipts without adding verdicts.
Run the recorder on the VM checkout, or copy the generated files into that checkout's
`fixtures/demo/` directory. Existing event fixtures and `web/public/fixtures/` are
independent test artifacts. No demo recordings ship in this PR; until recorded,
fixture mode returns `CHECK_INCOMPLETE` with an explicit **recording missing** reason.

To switch modes, set `DEMO_FIXTURE=1` in the VM's `.env`, then recreate the API:

```sh
export GIT_SHA=$(git rev-parse HEAD)
docker compose --env-file .env -f infra/compose.prod.yml up -d --force-recreate api
```

Production mounts `fixtures/demo/` read-only, so recordings can be installed without
rebuilding the image. Snapshots and every SSE payload identify recorded data with
`demo_fixture: true`, including jobs already referenced in `demo.json`. Recorded
streams replay over approximately two seconds and honor `Last-Event-ID`. Set the
flag back to `0` and recreate the API to restore real snapshots and execution.
Jobs created as fixtures keep their fixture provenance even after the flag is off.

`/status` reports uptime, git SHA (`GIT_SHA`, default `dev`), pipeline version, job
count and average terminal duration over the last hour, provider breaker states,
and UTC daily LLM spend against `LLM_DAILY_BUDGET`. Average duration includes queue
time and cached jobs. `infra/deploy.sh` supplies the deployed commit SHA.
Configure `LLM_INPUT_USD_PER_MILLION` and `LLM_OUTPUT_USD_PER_MILLION` with the rates
for your configured `REVIEW_MODEL`. Spend is calculated from returned token usage
and persisted across restarts. Missing usage/rates or failed accounting gives
`spend_usd: null`, a known subtotal, and `CHECK_INCOMPLETE`. Evidence checks continue
when costs are unknown. The budget guard stops new calls when known spend reaches
the threshold; in-flight calls can cross it. It is not a provider-side hard spending cap.

Crossref and OpenAlex have 10-second attempt deadlines, arXiv 20 seconds, and model
calls 60 seconds. Three consecutive failed HTTP attempts open that provider's
breaker for 60 seconds; one successful recovery probe closes it. If a provider is
down, inspect `/status` and API logs, wait for the probe, then retry with `--fresh`.
Affected receipts carry `CHECK_INCOMPLETE` or the schema's `NEEDS_REVIEW`/`UNKNOWN`
equivalent and a provider-specific reason. A provider outage does not abort the job.
For the presentation, use previously recorded demos with the fixture flag enabled.

After deploying with fixture mode disabled, validate the t3.large yourself:

```sh
.venv/bin/python scripts/load_test.py https://184-197-196-202.sslip.io -n 5
```

The load test bypasses cache, submits five jobs concurrently, and reports completed
jobs, failures, and nearest-rank p50/p95 end-to-end duration for successful jobs.
It returns nonzero for any failure or fixture response. Three jobs run at once and
the remainder queue. The limit is five uncached jobs per client IP per hour; run
this in a fresh quota window after warming, or wait for the prior jobs to age out.
Cached replays do not consume that allowance. Local tests use mocked providers;
no production jobs or server performance measurements were run for this PR.
