# Deployment

Plato has three deployable surfaces: the Python CLI (`plato …`), a FastAPI
backend (`plato.dashboard` package, default port `7878`), and a Next.js
frontend (`dashboard/frontend`, default port `3000`). This page covers
how to ship them together.

## Architectures

- **Single-user laptop** (default). One uvicorn + one Next.js dev server,
  no auth header required. Everything writes under `~/.plato/`.
- **Multi-tenant team**. Reverse proxy in front of the backend stamps an
  `X-Plato-User` header per request; storage namespaces under
  `<project_root>/users/<user_id>/`. Auth is enforced by the proxy, not
  by Plato itself.
- **Self-hosted Kubernetes**. Backend and frontend as separate Deployments
  behind an Ingress. Liveness/readiness against `/health` and `/ready`,
  PVC for `<project_root>` so runs survive pod restarts.
- **Vercel + serverless backend**. The Next.js frontend deploys cleanly
  to Vercel. The FastAPI backend assumes long-lived processes (LangGraph
  streams, SSE, `~/.plato/` state) and is **not** a fit for stateless
  serverless functions; run it on a long-running container target
  (Fly.io, Railway, Render, ECS, Cloud Run with min-instances ≥ 1).

## Single-user setup (5 minutes)

```bash
pip install plato
plato dashboard --port 7878
```

The dashboard command boots uvicorn and (if you've built the frontend)
serves it from the same process. For HMR during dev:

```bash
cd dashboard/frontend
npm install
npm run dev          # http://localhost:3000
```

LLM API keys go through the in-app `/keys` page — they're stored in
`~/.plato/keys.json` (encrypted with a host-derived salt). Environment
variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) are also picked
up if set.

## Multi-tenant setup (production)

Set these on the backend process:

| Variable | Purpose |
|---|---|
| `PLATO_DASHBOARD_AUTH_REQUIRED=1` | Reject any request that arrives without `X-Plato-User`. |
| `PLATO_PROJECT_ROOT` | Where per-user state lives. Mount on persistent storage. |
| `PLATO_RUN_TIMEOUT_SECONDS` | Hard ceiling on a single LangGraph stream (default `1800`). |
| `PLATO_RETRACTION_DB_PATH` | Optional path to a Crossref/Retraction Watch dump for citation validation. |
| `PLATO_TELEMETRY_DISABLED=1` | Disable the `~/.plato/telemetry.jsonl` sink (recommended for shared infra). |

The reverse proxy is responsible for setting `X-Plato-User`. Verified
options: Cloudflare Access (use the `Cf-Access-Authenticated-User-Email`
header rewritten to `X-Plato-User`), `oauth2-proxy` with
`--set-xauthrequest`, and nginx `auth_request` with
`proxy_set_header X-Plato-User $upstream_http_x_user`. The header value
must match `[A-Za-z0-9_.-]{1,64}`; longer or unsafe values are rejected
at the API edge.

Storage namespacing is automatic: every authed write resolves under
`<project_root>/users/<user_id>/`. The frontend's CSP is nonce-based and
configured per-request in `dashboard/frontend/src/middleware.ts` — no
extra setup. Probe `/health` for liveness, `/ready` for readiness
(checks `~/.plato/` writability and that `langgraph` imports).

## Container deployment

**Backend `Dockerfile`:**

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl tini ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir "plato[obs]"
ENV PLATO_PROJECT_ROOT=/data
EXPOSE 7878
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["plato", "dashboard", "--host", "0.0.0.0", "--port", "7878", "--no-browser"]
```

**Frontend `Dockerfile`** (Next.js standalone build):

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY dashboard/frontend/package*.json ./
RUN npm ci
COPY dashboard/frontend ./
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
ENV NEXT_PUBLIC_API_BASE=http://backend:7878/api/v1
EXPOSE 3000
CMD ["node", "server.js"]
```

**`docker-compose.yml`:**

```yaml
services:
  backend:
    build: { context: ., dockerfile: docker/Dockerfile.backend }
    environment:
      PLATO_DASHBOARD_AUTH_REQUIRED: "1"
      PLATO_PROJECT_ROOT: /data
      PLATO_TELEMETRY_DISABLED: "1"
    volumes: [ "plato-data:/data" ]
  frontend:
    build: { context: ., dockerfile: docker/Dockerfile.frontend }
    environment:
      NEXT_PUBLIC_API_BASE: http://backend:7878/api/v1
    depends_on: [ backend ]
  proxy:
    image: nginx:alpine
    volumes: [ "./nginx.conf:/etc/nginx/nginx.conf:ro" ]
    ports: [ "443:443" ]
    depends_on: [ frontend, backend ]
volumes:
  plato-data:
```

The proxy terminates TLS and stamps `X-Plato-User`; the backend never
sees raw user traffic.

## Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: plato-backend }
spec:
  replicas: 1
  selector: { matchLabels: { app: plato-backend } }
  template:
    metadata: { labels: { app: plato-backend } }
    spec:
      containers:
        - name: api
          image: ghcr.io/your-org/plato-backend:latest
          ports: [ { containerPort: 7878 } ]
          env:
            - { name: PLATO_DASHBOARD_AUTH_REQUIRED, value: "1" }
            - { name: PLATO_PROJECT_ROOT, value: /data }
          volumeMounts: [ { name: data, mountPath: /data } ]
          livenessProbe:
            httpGet: { path: /health, port: 7878 }
          readinessProbe:
            httpGet: { path: /ready, port: 7878 }
            initialDelaySeconds: 5
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: plato-data }
---
apiVersion: v1
kind: Service
metadata: { name: plato-backend }
spec:
  selector: { app: plato-backend }
  ports: [ { port: 7878, targetPort: 7878 } ]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: plato
  annotations:
    nginx.ingress.kubernetes.io/auth-url: https://auth.example.com/oauth2/auth
    nginx.ingress.kubernetes.io/auth-response-headers: X-Plato-User
spec:
  rules:
    - host: plato.example.com
      http:
        paths:
          - { path: /api,  pathType: Prefix, backend: { service: { name: plato-backend,  port: { number: 7878 } } } }
          - { path: /,     pathType: Prefix, backend: { service: { name: plato-frontend, port: { number: 3000 } } } }
```

A single replica is recommended for now: per-run state is on local disk
under the PVC, and the SQLite checkpointer is not safe for concurrent
writers from multiple pods. Use the Postgres checkpointer (ADR-0002)
when you need horizontal scaling.

## Environment variable reference

| Variable | Purpose | Default | Scope |
|---|---|---|---|
| `PLATO_DASHBOARD_AUTH_REQUIRED` | Require `X-Plato-User` header | unset (single-user) | backend |
| `PLATO_PROJECT_ROOT` | Per-user state root | `~/.plato/users` | backend |
| `PLATO_KEYS_PATH` | Override LLM keys store path | `~/.plato/keys.json` | backend |
| `PLATO_RUN_TIMEOUT_SECONDS` | Max LangGraph stream duration | `1800` | backend |
| `PLATO_RETRACTION_DB_PATH` | Citation retraction database | unset | backend |
| `PLATO_TELEMETRY_DISABLED` | Disable telemetry sink | unset | backend + CLI |
| `PLATO_DEMO_MODE` | `enabled` locks code-execution stages | `disabled` | backend |
| `NEXT_PUBLIC_API_BASE` | Backend URL for the SPA | `http://127.0.0.1:7878/api/v1` | frontend |

LLM provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GOOGLE_API_KEY`, etc.) are read by `key_store.py` if set in the
environment.

## Monitoring & observability

- **Telemetry sink**: `~/.plato/telemetry.jsonl` — one JSON line per run
  with cost, duration, and stage timings. Disable with
  `PLATO_TELEMETRY_DISABLED=1`.
- **Per-run manifest**: `<project_root>/<project>/runs/<run_id>/manifest.json`
  — full reproducibility record (model versions, prompt hashes, git SHA,
  artifact digests). See [features/manifest.md](features/manifest.md).
- **Langfuse (opt-in)**: `pip install plato[obs]`, then set
  `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` /
  `LANGFUSE_HOST` to ship traces to a Langfuse server.

## Observability — structured logs and request correlation

The dashboard backend ships a structured-logging stack
(`plato_dashboard.logging_config`) that the FastAPI lifespan installs
at startup. It does three things:

1. **JSON output by default.** When `python-json-logger` is installed
   the formatter renders one JSON object per line. When it's missing
   the stack falls back to a stdlib JSON formatter, and when
   `PLATO_LOG_JSON=0` it switches to a grep-friendly plain-text
   format. The dependency is lazy-imported, so no install bloat for
   users who don't need structured shipping.

2. **Request id correlation.** A `RequestLoggingMiddleware` mints a
   `request_id` for every request (or honours an upstream
   `X-Request-Id` header), binds it into a contextvar, logs request
   completion (`method`, `path`, `status`, `duration_ms`), and echoes
   the id back to the client via the `X-Request-Id` response header.
   Failed requests log at `ERROR` with a full traceback.

3. **Stable error envelope.** An `unhandled_exception_handler`
   catches anything that bubbles past the routes and returns
   `{"code": "internal_error", "request_id": "<id>"}` with a 500.
   The same id is logged with `request_id`, `user_id`, `run_id`,
   `exception_class`, `method`, `path`, and `traceback` extras so
   support staff can grep one id and reconstruct what happened.

### Log shape

```json
{
  "timestamp": "2026-05-03T12:00:00+00:00",
  "level": "INFO",
  "logger": "plato_dashboard.request",
  "message": "GET /api/v1/projects -> 200",
  "request_id": "8670deb05a9b4086822ca22a0db2183c",
  "user_id": "alice",
  "run_id": "-",
  "method": "GET",
  "path": "/api/v1/projects",
  "status": 200,
  "duration_ms": 12.4
}
```

`run_id` is populated when a request carries the `X-Plato-Run-Id`
header (set by the dashboard frontend) or when the worker has
already bound a run id via `plato.logging_config.run_id_var`.

### Configuration

| Env var | Default | Effect |
|---|---|---|
| `PLATO_LOG_LEVEL` | `INFO` | Standard `logging` level name |
| `PLATO_LOG_JSON` | `1` | `0` switches to plain text |

### Reading correlation ids from a route

```python
from fastapi import Request

@app.get("/example")
def example(request: Request) -> dict:
    return {"request_id": request.state.request_id}
```

The id also lives on the contextvar for log-shipping pipelines that
want to fan out into background tasks:

```python
from plato_dashboard.logging_config import request_id_var
import logging

logger = logging.getLogger(__name__)
logger.info("processing", extra={"request_id": request_id_var.get()})
```

The contextvar `extra` wins over the filter, so an explicit value
will always override what the middleware bound — useful in the
exception handler where contextvars have already been reset.

## Backup strategy

Back up:

- `<project_root>/` — projects, runs, manifests, per-user prefs.
- `~/.plato/telemetry.jsonl` — historical run accounting.
- `~/.plato/keys.json` — encrypted LLM keys (treat as a secret).

Don't back up `dashboard/frontend/.next/`, `__pycache__/`, or
`node_modules/` — they're regenerable build output and just bloat the
archive.

## Upgrade path

Pin a Plato version in your container image. New versions ship with a
[`CHANGELOG.md`](https://github.com/AstroPilot-AI/Plato/blob/master/CHANGELOG.md)
that calls out breaking changes. The SQLite checkpointer format has
been stable since ADR-0001; if you're on the Postgres checkpointer
(ADR-0002), run any LangGraph migration scripts called out in the
release notes before swapping the image.
