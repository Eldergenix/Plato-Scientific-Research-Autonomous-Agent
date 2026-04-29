# syntax=docker/dockerfile:1.7
# =============================================================================
# Plato Dashboard — HuggingFace Spaces (Docker SDK) image
# =============================================================================
# A leaner cousin of dashboard/Dockerfile that targets HF Spaces:
#   * EXPOSE 7860 (HF Spaces convention)
#   * Demo mode ON by default — code-execution stages locked, $0.50 cap
#   * Trimmed LaTeX install (HF Spaces enforces a ~50GB image cap and a
#     ~16GB persistent storage budget on the free tier)
#   * No bundled redis — fakeredis only (HF Spaces is single-process)
#
# Build context MUST be the repo root:
#   docker build -t plato-spaces -f dashboard/spaces/Dockerfile .
# =============================================================================


# -----------------------------------------------------------------------------
# Stage 1 — Frontend builder (identical to the prod Dockerfile)
# -----------------------------------------------------------------------------
FROM node:22-alpine AS frontend-builder

WORKDIR /build

COPY dashboard/frontend/package.json dashboard/frontend/package-lock.json ./
RUN npm ci

COPY dashboard/frontend/ ./
ENV NEXT_PUBLIC_API_BASE=/api/v1
ENV NEXT_TELEMETRY_DISABLED=1

RUN cat > next.config.ts <<'EOF'
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
EOF

RUN npm run build


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
    PLATO_PORT=7860 \
    PLATO_DEMO_MODE=enabled \
    PLATO_AUTH=disabled \
    PLATO_USE_FAKEREDIS=true \
    HOME=/home/plato

# <<< Slimmer apt set than the self-hosted image:
# only texlive-latex-recommended (no -extra, no -bibtex-extra, no -xetex).
# Demo mode disables paper-stage execution, so most BibTeX styles are dead
# weight on Spaces. tini stays for clean shutdown on SIGTERM.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
        curl \
        git \
        build-essential \
        texlive-latex-recommended \
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
RUN pip install -e .

# <<< Install dashboard backend.
COPY dashboard/backend/pyproject.toml /app/dashboard/backend/
COPY dashboard/backend/src/ /app/dashboard/backend/src/
RUN pip install -e /app/dashboard/backend

# <<< Pull the static frontend build.
COPY --from=frontend-builder /build/out /app/dashboard/frontend/out

# <<< HF-specific entrypoint script. Lives alongside the Dockerfile so users
# can tweak it without rebuilding. See dashboard/spaces/start.sh.
COPY dashboard/spaces/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-7860}/api/v1/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/start.sh"]
