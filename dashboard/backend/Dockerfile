# Plato dashboard backend — production image.
#
# Two-stage build:
#   1. builder: pulls Python deps with uv into a throwaway layer.
#   2. runtime: copies the resolved venv + source, runs uvicorn as a
#      non-root user.
#
# Build context is the repo root so the image can install both the
# dashboard backend (in dashboard/backend/) and the upstream `plato`
# package (in plato/) — the worker/langgraph_bridge imports it.
#
#   docker build -f dashboard/backend/Dockerfile -t plato-backend .

# ─── Stage 1: builder ────────────────────────────────────────────────
FROM python:3.12.7-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Build deps for any wheel that doesn't ship binaries (cryptography,
# pymupdf, etc.). Stripped from the runtime stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# Pin uv to a known release. uv resolves + installs orders of
# magnitude faster than pip and is what the project's lockfiles target.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /build

# Copy only the manifests first so dependency resolution caches when
# source files change but pyproject does not.
COPY pyproject.toml /build/pyproject.toml
COPY plato/__init__.py /build/plato/__init__.py
COPY dashboard/backend/pyproject.toml /build/dashboard/backend/pyproject.toml
COPY dashboard/backend/uv.lock /build/dashboard/backend/uv.lock

# Now the actual sources.
COPY plato /build/plato
COPY dashboard/backend/src /build/dashboard/backend/src
COPY README.md /build/README.md

# Single venv shared by the dashboard backend + the plato package it
# imports. uv pip install -e drops a .pth-style editable into the
# venv site-packages so the runtime stage just copies that venv.
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv pip install --no-cache /build \
    && uv pip install --no-cache /build/dashboard/backend

# ─── Stage 2: runtime ────────────────────────────────────────────────
FROM python:3.12.7-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PLATO_HOST=0.0.0.0 \
    PLATO_PORT=7878 \
    PLATO_PROJECT_ROOT=/data/projects \
    HOME=/home/plato

# curl for the HEALTHCHECK; tini for clean signal forwarding so
# uvicorn shuts down on docker stop instead of getting SIGKILLed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — uid/gid 10001 to stay clear of host /etc/passwd
# collisions. /data and /home/plato are owned by it so the volume
# mounts work without --user-on-host gymnastics.
RUN groupadd --system --gid 10001 plato \
    && useradd --system --uid 10001 --gid plato --create-home --home-dir /home/plato plato \
    && mkdir -p /data/projects /home/plato/.plato \
    && chown -R plato:plato /data /home/plato

# Pull the resolved venv and the source tree from the builder.
COPY --from=builder --chown=plato:plato /opt/venv /opt/venv
COPY --from=builder --chown=plato:plato /build/plato /app/plato
COPY --from=builder --chown=plato:plato /build/dashboard/backend/src /app/src

WORKDIR /app
USER plato

EXPOSE 7878

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:7878/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "plato_dashboard.api.server:app", "--host", "0.0.0.0", "--port", "7878"]
