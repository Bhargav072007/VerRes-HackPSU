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
