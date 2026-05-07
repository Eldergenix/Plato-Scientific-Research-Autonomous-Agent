# syntax=docker/dockerfile:1.7
# =============================================================================
# Plato Dashboard — Self-hosted production image
# =============================================================================
# Multi-stage build:
#   1. frontend-builder : Next.js 15 production build under node:22-slim
#   2. node-runtime     : donates a glibc Node binary to the Python image
#   3. runtime          : python:3.13-slim + LaTeX (xelatex, BibTeX, etc.)
#                          runs FastAPI internally and Next.js publicly.
#
# Build context MUST be the repo root (parent of the dashboard/ directory),
# because we install the parent `plato` package via `pip install -e .`.
#
#   docker build -t plato-dashboard:latest -f dashboard/Dockerfile .
#
# Estimated image size: ~2.0-2.4 GB (LaTeX dominates; Python deps ~400 MB,
# Node runtime + Next.js dependencies add the rest).
# =============================================================================


# -----------------------------------------------------------------------------
# Stage 1 — Frontend builder
# -----------------------------------------------------------------------------
FROM node:22-slim AS frontend-builder

WORKDIR /build

# <<< Install JS dependencies first so they are cached independently of the
# rest of the source tree. Lockfile-based install for reproducibility.
COPY dashboard/frontend/package.json dashboard/frontend/package-lock.json ./

# Network-resilient npm install. Build-VM CDN egress is flaky enough that
# the default 5 min fetch-timeout / 2 retries occasionally trips ETIMEDOUT
# (exit 146). Stretch the budget to 10 min × 5 retries and drop the audit/
# fund lookups — those add a registry round-trip per package and do not
# influence the build artifact.
RUN npm config set fetch-timeout 600000 \
 && npm config set fetch-retries 5 \
 && npm config set fetch-retry-mintimeout 20000 \
 && npm config set fetch-retry-maxtimeout 120000 \
 && npm ci --prefer-offline --no-audit --no-fund

# <<< Copy frontend source and inject build-time env.
# NEXT_PUBLIC_API_BASE points at the same origin. Next.js receives /api/v1
# and proxies those requests to the internal FastAPI process.
COPY dashboard/frontend/ ./
ENV NEXT_PUBLIC_API_BASE=/api/v1
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build


# -----------------------------------------------------------------------------
# Stage 2 — Node runtime donor
# -----------------------------------------------------------------------------
FROM node:22-slim AS node-runtime


# -----------------------------------------------------------------------------
# Stage 3 — Runtime
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLATO_HOST=0.0.0.0 \
    PLATO_PORT=7879 \
    PLATO_BACKEND_PORT=7879

# <<< System dependencies.
# We mirror the parent docker/Dockerfile.prod LaTeX stack so paper-stage
# generation works end-to-end (xelatex + recommended BibTeX styles).
# tini is PID 1 for signal handling; redis-server is optional (used only
# when PLATO_USE_FAKEREDIS is disabled); build-essential + git are needed
# by cmbagent's C extensions during pip install.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
        curl \
        git \
        build-essential \
        redis-server \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-bibtex-extra \
        texlive-xetex \
        lmodern && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# <<< Install the parent Plato package first.
# Copying pyproject.toml and the plato/ package separately keeps the deps
# layer warm even when only application code changes.
COPY pyproject.toml README.md /app/
COPY plato/ /app/plato/
RUN pip install -e .

# <<< Install the dashboard backend (editable so log/event paths resolve).
COPY dashboard/backend/pyproject.toml /app/dashboard/backend/
COPY dashboard/backend/src/ /app/dashboard/backend/src/
RUN pip install -e /app/dashboard/backend

# <<< Pull the Next.js production build out of stage 1.
COPY --from=frontend-builder /build/package.json /app/dashboard/frontend/package.json
COPY --from=frontend-builder /build/package-lock.json /app/dashboard/frontend/package-lock.json
COPY --from=frontend-builder /build/next.config.ts /app/dashboard/frontend/next.config.ts
COPY --from=frontend-builder /build/public /app/dashboard/frontend/public
COPY --from=frontend-builder /build/.next /app/dashboard/frontend/.next
COPY --from=frontend-builder /build/node_modules /app/dashboard/frontend/node_modules

# <<< Entrypoint shim — starts redis (when needed), FastAPI internally,
# then Next.js on the public port under tini.
RUN cat > /usr/local/bin/plato-entrypoint.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

PUBLIC_PORT="${PORT:-7878}"
BACKEND_PORT="${PLATO_BACKEND_PORT:-7879}"
export PLATO_PORT="${BACKEND_PORT}"
export PLATO_API_PROXY_TARGET="${PLATO_API_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

# Only spin up a real Redis when explicitly requested. The default
# (PLATO_USE_FAKEREDIS=true) keeps the container single-process.
if [[ "${PLATO_USE_FAKEREDIS:-true}" == "false" || "${PLATO_USE_FAKEREDIS:-true}" == "disabled" ]]; then
    echo "[entrypoint] Starting redis-server in background"
    redis-server --daemonize yes --bind 127.0.0.1 --port 6379 --save "" --appendonly no
fi

echo "[entrypoint] Launching FastAPI on 127.0.0.1:${BACKEND_PORT}"
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
        echo "[entrypoint] FastAPI did not become healthy" >&2
        exit 1
    fi
    sleep 1
done

cd /app/dashboard/frontend
echo "[entrypoint] Launching Next.js on 0.0.0.0:${PUBLIC_PORT}"
node node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port "${PUBLIC_PORT}" &
next_pid="$!"

set +e
wait -n "${api_pid}" "${next_pid}"
status="$?"
set -e
cleanup
wait "${api_pid}" "${next_pid}" 2>/dev/null || true
exit "${status}"
EOF
RUN chmod +x /usr/local/bin/plato-entrypoint.sh

EXPOSE 7878

# <<< Healthcheck hits the FastAPI health endpoint. Generous start-period
# because LaTeX-bearing images take a beat to warm.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-7878}/api/v1/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/plato-entrypoint.sh"]
