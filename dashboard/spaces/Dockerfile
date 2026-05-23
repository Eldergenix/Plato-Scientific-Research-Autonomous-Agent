# syntax=docker/dockerfile:1.7
# =============================================================================
# Plato Dashboard — HuggingFace Spaces (Docker SDK) image
# =============================================================================
# A leaner cousin of dashboard/Dockerfile that targets HF Spaces:
#   * EXPOSE 7860 (HF Spaces convention)
#   * Demo mode ON by default — code-execution stages locked, $0.50 cap
#   * LaTeX install includes xelatex so hosted paper generation can compile PDFs
#   * No bundled redis — fakeredis only (HF Spaces gets one container)
#
# Build context MUST be the repo root:
#   docker build -t plato-spaces -f dashboard/spaces/Dockerfile .
# =============================================================================


# -----------------------------------------------------------------------------
# Stage 1 — Frontend builder (identical to the prod Dockerfile)
# -----------------------------------------------------------------------------
FROM node:22-slim AS frontend-builder

WORKDIR /build

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
    PIP_ROOT_USER_ACTION=ignore \
    PLATO_HOST=0.0.0.0 \
    PLATO_PORT=7878 \
    PLATO_BACKEND_PORT=7878 \
    PLATO_DEMO_MODE=enabled \
    PLATO_AUTH=disabled \
    PLATO_USE_FAKEREDIS=true \
    HOME=/home/plato

# <<< Keep the LaTeX stack aligned with dashboard/Dockerfile. Production
# Railway uses this image too, and paper-stage execution requires xelatex.
# The python slim base excludes man pages; TeX/xz update-alternatives expects
# them, so restore docs before apt install to keep production builds quiet.
RUN rm -f /etc/dpkg/dpkg.cfg.d/docker && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
        curl \
        git \
        build-essential \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-bibtex-extra \
        texlive-xetex \
        lmodern && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# <<< HF Spaces injects a non-root user but the image still builds as root.
# Create a writable home and project dir up front so the runtime user can
# persist project state without a chown step on every cold start.
RUN mkdir -p /home/plato/.plato/projects && chmod -R 0777 /home/plato

WORKDIR /app

# <<< Install parent Plato.
COPY pyproject.toml README.md /app/
COPY plato/ /app/plato/
RUN pip install -q -e .

# <<< Install dashboard backend.
COPY dashboard/backend/pyproject.toml /app/dashboard/backend/
COPY dashboard/backend/src/ /app/dashboard/backend/src/
RUN pip install -q -e /app/dashboard/backend

# <<< Pull the Next.js production build. The public process is Next; the
# FastAPI gateway runs on an internal localhost port and handles /api/v1.
COPY --from=frontend-builder /build/package.json /app/dashboard/frontend/package.json
COPY --from=frontend-builder /build/package-lock.json /app/dashboard/frontend/package-lock.json
COPY --from=frontend-builder /build/next.config.ts /app/dashboard/frontend/next.config.ts
COPY --from=frontend-builder /build/public /app/dashboard/frontend/public
COPY --from=frontend-builder /build/.next /app/dashboard/frontend/.next
COPY --from=frontend-builder /build/node_modules /app/dashboard/frontend/node_modules

# <<< HF-specific entrypoint script. Lives alongside the Dockerfile so users
# can tweak it without rebuilding. See dashboard/spaces/start.sh.
COPY dashboard/spaces/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-7860}/api/v1/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/start.sh"]
