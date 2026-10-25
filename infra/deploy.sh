#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Print diagnostics on success and failure without dumping environment values.
trap 'docker compose --env-file .env -f infra/compose.prod.yml logs --tail 50 --no-color api || true' EXIT
git pull --ff-only
api_domain=$(docker compose --env-file .env -f infra/compose.prod.yml config --format json |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["services"]["caddy"]["environment"]["API_DOMAIN"])')
docker compose --env-file .env -f infra/compose.prod.yml up -d --build

echo "Waiting up to 10 minutes for https://${api_domain}/health"
deadline=$((SECONDS + 600))
while (( SECONDS < deadline )); do
    if curl --fail --silent --connect-timeout 5 --max-time 15 "https://${api_domain}/health" >/dev/null; then
        echo "API is healthy: https://${api_domain}/health"
        exit 0
    fi
    sleep 5
done
echo "Health check timed out; inspect API, GROBID and Caddy logs." >&2
exit 1
