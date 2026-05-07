#!/usr/bin/env bash
# =============================================================================
# HuggingFace Spaces entrypoint for the Plato Dashboard.
# Invoked from dashboard/spaces/Dockerfile via tini.
# =============================================================================
set -euo pipefail

# Demo mode is the safe default on a public Space. Operators can flip this
# to "disabled" by setting PLATO_DEMO_MODE in the Space "Variables" panel
# (NOT "Secrets" — those don't propagate to the build env).
export PLATO_DEMO_MODE="${PLATO_DEMO_MODE:-enabled}"

# HF Spaces and Railway set $PORT for the public process. FastAPI runs on
# localhost, while Next.js serves the app and proxies /api/v1 to FastAPI.
PUBLIC_PORT="${PORT:-7860}"
BACKEND_PORT="${PLATO_BACKEND_PORT:-7878}"
export PLATO_PORT="${BACKEND_PORT}"
export PLATO_API_PROXY_TARGET="${PLATO_API_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

uvicorn plato_dashboard.api.server:app \
    --host 0.0.0.0 \
    --port "${BACKEND_PORT}" \
    --proxy-headers \
    --forwarded-allow-ips='*' &
api_pid="$!"

cleanup() {
    kill "${api_pid}" "${next_pid:-}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

for i in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" >/dev/null; then
        break
    fi
    if [[ "${i}" == "60" ]]; then
        echo "[start] FastAPI did not become healthy" >&2
        exit 1
    fi
    sleep 1
done

cd /app/dashboard/frontend
node node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port "${PUBLIC_PORT}" &
next_pid="$!"

set +e
wait -n "${api_pid}" "${next_pid}"
status="$?"
set -e
cleanup
wait "${api_pid}" "${next_pid}" 2>/dev/null || true
exit "${status}"
