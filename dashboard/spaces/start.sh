#!/usr/bin/env bash
# =============================================================================
# HuggingFace Spaces entrypoint for the Plato Dashboard.
# Invoked from dashboard/spaces/Dockerfile via tini.
# =============================================================================
# Iter-11: ``set -e`` alone misses unset-variable expansions and
# pipeline-mid failures. Match the standalone Dockerfile entrypoint
# which uses ``set -euo pipefail`` so a partial failure aborts
# instead of silently exiting 0.
set -euo pipefail

# Demo mode is the safe default on a public Space. Operators can flip this
# to "disabled" by setting PLATO_DEMO_MODE in the Space "Variables" panel
# (NOT "Secrets" — those don't propagate to the build env).
export PLATO_DEMO_MODE="${PLATO_DEMO_MODE:-enabled}"

# HF Spaces sets $PORT itself; PLATO_PORT mirrors it for the settings module.
export PLATO_PORT="${PORT:-7860}"

exec uvicorn plato_dashboard.api.server:app \
    --host 0.0.0.0 \
    --port "${PLATO_PORT}" \
    --proxy-headers \
    --forwarded-allow-ips='*'
