#!/usr/bin/env bash
# Run every end-to-end suite against local services: the Python service, wrangler dev, the
# Anthropic and Composio stubs and Postgres. Used by CI (.github/workflows/scientist.yml)
# and locally:
#
#   PLATO_E2E_DSN=postgresql://postgres:postgres@127.0.0.1:5432/postgres \
#   PLATO_E2E_PYTHON=/path/to/venv/bin/python  cloudflare/plato-scientist/e2e/run-all.sh /tmp/plato-e2e
#
# Needs: npm ci in cloudflare/plato-scientist, Playwright's Chromium, a Python with
# docker/requirements-scientist.txt, pdflatex and pandoc 3.1.3 (review and publish suites),
# and a local Postgres the DSN's role may write. Screenshots and service logs go to $1.
# Exits non-zero if any suite fails; every suite runs either way. PLATO_E2E_ONLY="ui api"
# runs only the named suites.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=$(mkdir -p "${1:-/tmp/plato-e2e}" && cd "${1:-/tmp/plato-e2e}" && pwd)
DSN=${PLATO_E2E_DSN:-postgresql://postgres:postgres@127.0.0.1:5432/postgres}
PY=${PLATO_E2E_PYTHON:-python3}
case "$DSN" in *@127.0.0.1[:/]* | *@localhost[:/]*) ;; *) echo "PLATO_E2E_DSN must be local" >&2; exit 2 ;; esac
SECRET=$(openssl rand -hex 16)
export WRANGLER_SEND_METRICS=false CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE="$DSN"

for port in 8080 8787 8790 8791; do # a server left on a port would answer for ours
  if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/"; then echo "port $port is already in use" >&2; exit 2; fi
done

# Each service runs in its own process group so cleanup also stops wrangler's workerd children.
pids=()
start() { setsid "$@" & pids+=($!); }
cleanup() { for p in "${pids[@]}"; do kill -- "-$p" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT

start node e2e/stub-anthropic.mjs "$OUT/stub-requests.jsonl" >"$OUT/stub-anthropic.log" 2>&1
start node e2e/stub-composio.mjs 8791 >"$OUT/stub-composio.log" 2>&1
# The service applies the migrations on start.
start env -C ../.. PLATO_DATABASE_URL="$DSN" PLATO_INTERNAL_TOKEN=dev ANTHROPIC_API_KEY=sk-ant-default-0000 \
  ANTHROPIC_BASE_URL=http://127.0.0.1:8790 PYTHONPATH=. "$PY" -m plato.scientist.service \
  >"$OUT/service.log" 2>&1
start npx wrangler dev --ip 127.0.0.1 --port 8787 --enable-containers=false \
  --var PLATO_API_TOKEN:dev --var PLATO_INTERNAL_TOKEN:dev \
  --var "PLATO_SECRETS_KEY:$(openssl rand -base64 32)" --var ANTHROPIC_API_KEY:sk-ant-default-0000 \
  --var PLATO_DEV_SERVICE_URL:http://127.0.0.1:8080 \
  --var PLATO_DEV_ANTHROPIC_BASE_URL:http://127.0.0.1:8790 \
  --var PLATO_DEV_COMPOSIO_BASE_URL:http://127.0.0.1:8791 --var COMPOSIO_API_KEY:ak_stub \
  --var "COMPOSIO_WEBHOOK_SECRET:$SECRET" --var PLATO_DEFAULT_MONTHLY_TOKENS:1500000 \
  >"$OUT/wrangler.log" 2>&1

wait_for() {
  for _ in $(seq 1 180); do curl -sf -o /dev/null "$1" && return 0; sleep 1; done
  echo "timed out waiting for $1" >&2
  tail -n 40 "$OUT"/*.log >&2
  exit 1
}
wait_for http://127.0.0.1:8080/healthz
wait_for http://127.0.0.1:8787/api/me

reset_throttle() { # sign-up is throttled per IP; every suite signs up
  "$PY" -c 'import asyncio, asyncpg, sys
async def main():
    c = await asyncpg.connect(sys.argv[1]); await c.execute("DELETE FROM plato.auth_attempts"); await c.close()
asyncio.run(main())' "$DSN"
}

failed=()
run() {
  local name=$1
  shift
  # PLATO_E2E_ONLY="ui data" runs just those suites (to re-run failures).
  if [[ -n "${PLATO_E2E_ONLY:-}" && " $PLATO_E2E_ONLY " != *" $name "* ]]; then return; fi
  reset_throttle
  echo "::group::$name"
  if env PLATO_DATABASE_URL="$DSN" PLATO_E2E_DSN="$DSN" PLATO_E2E_PYTHON="$PY" \
    COMPOSIO_WEBHOOK_SECRET="$SECRET" "$@"; then
    echo "::endgroup::"
    echo "PASS $name"
  else
    echo "::endgroup::"
    echo "FAIL $name"
    failed+=("$name")
  fi
}
run unit node e2e/unit.test.mjs
run api node e2e/api.test.mjs "$OUT/stub-requests.jsonl"
run ui node e2e/ui.test.cjs "$OUT"
run integrations node e2e/integrations.test.mjs
run publish-ui node e2e/publish-ui.test.cjs "$OUT"
run review-ui node e2e/review-ui.test.cjs "$OUT"
run data node e2e/data.test.cjs "$OUT"
run graph-hover node e2e/graph-hover.test.cjs public "$OUT"

if ((${#failed[@]})); then
  echo "Failed suites: ${failed[*]}" >&2
  exit 1
fi
echo "All end-to-end suites passed."
