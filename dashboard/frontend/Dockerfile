# Plato dashboard frontend — production image.
#
# Two-stage build using Next.js standalone output. Stage 1 runs
# `npm ci && npm run build`, stage 2 copies the standalone server +
# static assets and runs them as a non-root user.
#
# Build context is dashboard/frontend/.
#
#   docker build \
#     -f dashboard/frontend/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_BASE=http://backend:7878 \
#     -t plato-frontend dashboard/frontend
#
# NOTE: requires `output: "standalone"` in next.config.ts. The
# compose file passes the build-arg; the production target hostname is
# whatever Caddy sees as the backend service.

# ─── Stage 1: builder ────────────────────────────────────────────────
FROM node:20.18.1-bookworm-slim AS builder

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

# NEXT_PUBLIC_* values are baked at build time, not runtime, so we
# need this here rather than in the runtime stage. Default points at
# the in-cluster service name; override per environment.
ARG NEXT_PUBLIC_API_BASE=http://backend:7878
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}

WORKDIR /build

# Cache the npm install layer until lockfiles change.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Now the actual sources.
COPY . .

RUN npm run build

# ─── Stage 2: runtime ────────────────────────────────────────────────
FROM node:20.18.1-bookworm-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# tini for signal handling; node alone doesn't reap zombies.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Reuse the `node` user the upstream image already creates (uid 1000)
# rather than inventing a second non-root account.
RUN mkdir -p /app && chown -R node:node /app

WORKDIR /app
USER node

# .next/standalone is the self-contained server (server.js + minimal
# node_modules). Static assets and public/ are not bundled into it.
COPY --from=builder --chown=node:node /build/.next/standalone ./
COPY --from=builder --chown=node:node /build/.next/static ./.next/static
COPY --from=builder --chown=node:node /build/public ./public

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "server.js"]
