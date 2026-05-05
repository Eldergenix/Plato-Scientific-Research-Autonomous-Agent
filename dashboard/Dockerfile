# syntax=docker/dockerfile:1.7
# =============================================================================
# Plato Dashboard — Self-hosted production image
# =============================================================================
# Multi-stage build:
#   1. frontend-builder : Next.js 15 static export under node:22-alpine
#   2. runtime          : python:3.13-slim + LaTeX (xelatex, BibTeX, etc.)
#                          serves the FastAPI gateway and the static frontend
#                          out of a single container.
#
# Build context MUST be the repo root (parent of the dashboard/ directory),
# because we install the parent `plato` package via `pip install -e .`.
#
#   docker build -t plato-dashboard:latest -f dashboard/Dockerfile .
#
# Estimated image size: ~1.7-2.0 GB (LaTeX dominates; Python deps ~400 MB,
# Node static export ~30 MB, base image ~120 MB).
# =============================================================================


# -----------------------------------------------------------------------------
# Stage 1 — Frontend builder
# -----------------------------------------------------------------------------
FROM node:22-alpine AS frontend-builder

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
# NEXT_PUBLIC_API_BASE points at the *same origin* (FastAPI mounts the static
# export at "/"), so we use a relative path to avoid baking in a hostname.
COPY dashboard/frontend/ ./
ENV NEXT_PUBLIC_API_BASE=/api/v1
ENV NEXT_TELEMETRY_DISABLED=1

# <<< Force Next.js into static export mode at build time.
# We rewrite next.config.ts to set `output: 'export'` so `next build`
# produces an /out directory of pure static HTML/JS that FastAPI can serve.
# Trade-off: server actions, ISR, and dynamic API routes inside Next are
# disabled — but the dashboard frontend is a thin client that talks to the
# FastAPI backend over HTTP, so this is a net win (smaller image, no node
# runtime in production).
RUN cat > next.config.ts <<'EOF'
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
EOF

# <<< Use webpack-based `next build` directly. The package.json script is
# `next build --turbopack`, but Next.js 15 Turbopack does not yet resolve
# tsconfig.json `paths` aliases (e.g. "@/*") under `output: "export"` mode,
# which causes module-not-found errors on every `@/components/...` import.
# `npx next build` invokes the binary without --turbopack, falling back to
# webpack which resolves paths correctly.
RUN npx next build


# -----------------------------------------------------------------------------
# Stage 2 — Runtime
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLATO_HOST=0.0.0.0 \
    PLATO_PORT=7878

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

# <<< Pull the static frontend build out of stage 1.
# The backend looks here at runtime: see api/server.py — it mounts
# /app/dashboard/frontend/out at "/" only when this directory exists.
COPY --from=frontend-builder /build/out /app/dashboard/frontend/out

# <<< Entrypoint shim — starts redis (when needed) then uvicorn under tini.
# Honors $PORT for HuggingFace Spaces / Cloud Run compatibility while
# defaulting to PLATO_PORT (7878) for self-hosted use.
RUN cat > /usr/local/bin/plato-entrypoint.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-${PLATO_PORT:-7878}}"
export PLATO_PORT="${PORT}"

# Only spin up a real Redis when explicitly requested. The default
# (PLATO_USE_FAKEREDIS=true) keeps the container single-process.
if [[ "${PLATO_USE_FAKEREDIS:-true}" == "false" || "${PLATO_USE_FAKEREDIS:-true}" == "disabled" ]]; then
    echo "[entrypoint] Starting redis-server in background"
    redis-server --daemonize yes --bind 127.0.0.1 --port 6379 --save "" --appendonly no
fi

echo "[entrypoint] Launching plato-dashboard on 0.0.0.0:${PORT}"
exec uvicorn plato_dashboard.api.server:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --proxy-headers \
    --forwarded-allow-ips='*'
EOF
RUN chmod +x /usr/local/bin/plato-entrypoint.sh

EXPOSE 7878

# <<< Healthcheck hits the FastAPI health endpoint. Generous start-period
# because LaTeX-bearing images take a beat to warm.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-${PLATO_PORT:-7878}}/api/v1/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/plato-entrypoint.sh"]
