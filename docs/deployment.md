# Plato Dashboard — Deployment Runbook

This is the operations guide for self-hosting the Plato dashboard from
the production image at `dashboard/Dockerfile`. It covers building,
running, persistence, observability, and recovery.

For development setup see [`dashboard/README.md`](../dashboard/README.md).
For the public-demo (Railway / HuggingFace Spaces) shape see
[`dashboard/RAILWAY.md`](../dashboard/RAILWAY.md).

---

## 1. Overview

The image is a single container that bundles:

- **FastAPI gateway** (`plato_dashboard.api.server:app`) — REST + SSE on
  port 7878, mounts the static frontend at `/`.
- **Next.js static export** — built in stage 1 (node:22-alpine), copied
  into the runtime stage as `/app/dashboard/frontend/out`. No Node
  process runs in production.
- **LaTeX (TeX Live)** — `xelatex`, recommended/extra/bibtex/xetex
  packages plus `lmodern` so the paper stage can compile.
- **Quarkdown** — JDK 17 + Node + Chromium for the four-doctype
  hybrid renderer (paged book, slides, docs, one-pager). Pinned by
  version + sha256 (Wave 4 hardening; see `dashboard/Dockerfile:140`).
- **redis-server** — installed but only started when
  `PLATO_USE_FAKEREDIS=false`. Default keeps the container
  single-process via fakeredis.

**Image size**: ~1.7–2.0 GB. LaTeX dominates (~1.2 GB), followed by
Python deps (~400 MB), the JDK (~200 MB), Chromium (~150 MB).

**Cold start**: budget ~30 seconds before the first health probe
succeeds. The healthcheck shells out to `quarkdown --version`, which
spins up the JVM; `--start-period=30s` in the Dockerfile accounts for
this. Subsequent renders reuse the JVM only if you keep a long-lived
Quarkdown daemon, which we don't — every render pays a ~3 s JVM
startup tax. Tune your render timeout accordingly.

---

## 2. Prerequisites

| Component | Version | Required? |
|---|---|---|
| Docker Engine | 24+ | yes (BuildKit / `RUN --mount` syntax) |
| docker buildx | bundled with 24+ | yes |
| Disk for image | ~2.5 GB free | yes |
| Disk for `~/.plato` volume | grows with usage; budget 2 GB/project | yes |
| Postgres | n/a | not required (Plato persists to disk; no DB) |
| Redis | 7+ | optional — default uses fakeredis |
| Reverse proxy | nginx / Caddy / Traefik | recommended for TLS + SSE |

There is **no Postgres dependency** today. Project state, run
manifests, key store, and event history live on disk under
`~/.plato/`. Redis is optional and only needed for cross-process
fan-out, which a single-container deployment doesn't have.

---

## 3. Build

The image pins Quarkdown to a specific release archive and verifies
its sha256. You must compute the digest at build time.

### Compute the Quarkdown sha256

```bash
QUARKDOWN_VERSION=2.0.1
QUARKDOWN_SHA256=$(curl -fsSL \
  "https://github.com/iamgio/quarkdown/releases/download/v${QUARKDOWN_VERSION}/quarkdown.zip" \
  | sha256sum | awk '{print $1}')
echo "$QUARKDOWN_SHA256"
```

This is exactly what
[`.github/workflows/dashboard-build.yml`](../.github/workflows/dashboard-build.yml)
does in CI (see the `Compute Quarkdown SHA256` step). For a different
Quarkdown version, change `QUARKDOWN_VERSION` and recompute.

### Build the image

The build context **must be the repo root** (the parent of `dashboard/`)
because the Dockerfile installs the parent `plato` Python package via
`pip install -e .`.

```bash
cd "$(git rev-parse --show-toplevel)"

docker buildx build \
  --build-arg QUARKDOWN_VERSION=2.0.1 \
  --build-arg "QUARKDOWN_SHA256=${QUARKDOWN_SHA256}" \
  --file dashboard/Dockerfile \
  --tag plato-dashboard:$(git rev-parse --short HEAD) \
  --tag plato-dashboard:latest \
  --load \
  .
```

If you forget `QUARKDOWN_SHA256`, the build aborts at the
`sha256sum -c -` step in the Quarkdown stage with a clear mismatch
error. That is the intended behavior — see
[`dashboard/Dockerfile:140-155`](../dashboard/Dockerfile).

Expected build time: 8–15 minutes cold, 1–3 minutes warm.

---

## 4. Run

Single-container, with a named volume for state:

```bash
docker volume create plato-data

docker run -d \
  --name plato-dashboard \
  --restart unless-stopped \
  -p 7878:7878 \
  -v plato-data:/root/.plato \
  -e PLATO_USE_FAKEREDIS=true \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  plato-dashboard:latest
```

The container exposes `7878` and listens on `0.0.0.0` inside; bind it
behind a reverse proxy that terminates TLS. The healthcheck already
hits `/api/v1/health`; Docker will mark the container `unhealthy`
within ~90 s if either FastAPI or Quarkdown stops responding.

### `$PORT` overrides (Cloud Run / Spaces)

The entrypoint honors `$PORT` if the platform sets it (e.g. Cloud Run,
HuggingFace Spaces). Otherwise it falls back to `PLATO_PORT`
(default 7878). See the entrypoint shim in
[`dashboard/Dockerfile:170-190`](../dashboard/Dockerfile).

---

## 5. docker-compose

The repo's [`compose.yaml`](../compose.yaml) is for the **legacy
Streamlit app** (port 8501, `docker/Dockerfile.dev`), not the
dashboard. Use this minimal compose for the dashboard:

```yaml
# docker-compose.dashboard.yaml
services:
  plato-dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
      args:
        QUARKDOWN_VERSION: 2.0.1
        QUARKDOWN_SHA256: ${QUARKDOWN_SHA256:?compute via curl + sha256sum}
    image: plato-dashboard:latest
    restart: unless-stopped
    ports:
      - "7878:7878"
    volumes:
      - plato-data:/root/.plato
    environment:
      PLATO_USE_FAKEREDIS: "true"
      PLATO_OBS_JSON_LOGS: "1"
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:7878/api/v1/health"]
      interval: 30s
      timeout: 10s
      start_period: 30s
      retries: 3

volumes:
  plato-data:
```

Run with `QUARKDOWN_SHA256=... docker compose -f docker-compose.dashboard.yaml up -d`.

---

## 6. Environment variables

Cross-reference with [`.env.example`](../.env.example).

### LLM providers

| Name | Default | Description | Security |
|---|---|---|---|
| `OPENAI_API_KEY` | unset | OpenAI completions / embeddings | secret |
| `ANTHROPIC_API_KEY` | unset | Anthropic completions | secret |
| `GOOGLE_API_KEY` | unset | Gemini / Google AI Studio | secret |
| `PERPLEXITY_API_KEY` | unset | Perplexity for retrieval | secret |
| `GOOGLE_APPLICATION_CREDENTIALS` | unset | Path to GCP service-account JSON inside the container | secret (mount file r/o) |

Plato runs in degraded "demo" mode if every provider key is missing —
no real LLM calls. Keys configured via the `/keys` UI are stored
encrypted under `~/.plato/keys.json` (or per-user — see §12) and take
effect only when the matching env var is unset.

### Retrieval adapters

| Name | Default | Description | Security |
|---|---|---|---|
| `SEMANTIC_SCHOLAR_KEY` | unset | Higher rate limit for Semantic Scholar | secret |
| `ADS_API_KEY` | unset | NASA ADS retrieval | secret |
| `NCBI_API_KEY` | unset | PubMed retrieval | secret |
| `FUTURE_HOUSE_API_KEY` | unset | FutureHouse retrieval | secret |

### Dashboard runtime

| Name | Default | Description | Security |
|---|---|---|---|
| `PLATO_HOST` | `0.0.0.0` (in container) | uvicorn bind host | safe |
| `PLATO_PORT` | `7878` | uvicorn port; overridden by `$PORT` if set | safe |
| `PLATO_PROJECT_ROOT` | `~/.plato/projects` | Override project filesystem root | safe |
| `PLATO_KEYS_PATH` | `~/.plato/keys.json` | Override key-store path | safe |
| `PLATO_DASHBOARD_AUTH_REQUIRED` | `0` | When `1`, every request must carry `X-Plato-User` and storage is per-user namespaced | **flip to `1` for multi-tenant** |
| `PLATO_DEMO_MODE` | `0` (`disabled`) | `enabled` locks code-executing stages and applies $-cap | safe |
| `PLATO_USE_FAKEREDIS` | `true` | When `false`/`disabled`, the entrypoint starts redis-server in the container | safe |
| `PLATO_DISABLE_RETRIEVAL_CACHE` | `0` | Skip the on-disk ETag cache (testing only) | safe |
| `PLATO_EVAL_MAX_USD` | `20` | Hard $-cap for nightly eval workflow | safe |

### Observability

| Name | Default | Description | Security |
|---|---|---|---|
| `PLATO_OBS_JSON_LOGS` | unset | Set `1` to emit structured JSON logs (parsed by Loki / Datadog / CloudWatch) | safe |
| `SENTRY_DSN` | unset | Wires Sentry if `sentry-sdk` is installed | secret-ish (DSN is semi-public) |
| `LANGFUSE_PUBLIC_KEY` | unset | Langfuse trace shipping | secret |
| `LANGFUSE_SECRET_KEY` | unset | Langfuse trace shipping | secret |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Self-hosted Langfuse override | safe |

`PLATO_OBS_JSON_LOGS` is read in
`plato_dashboard/observability/__init__.py:27`. `SENTRY_DSN` is read in
`plato_dashboard/api/server.py:388` and a warning is logged if the DSN
is set but `sentry-sdk` is not installed.

### Removed in 0.2

- `ADS_DEV_KEY` → use `ADS_API_KEY`.
- `PLATO_AUTH` → superseded by `PLATO_DASHBOARD_AUTH_REQUIRED`.

---

## 7. Health checks

| Endpoint | Method | Codes | Use |
|---|---|---|---|
| `/api/v1/health` | GET | 200 normal, 503 during shutdown drain | k8s liveness + readiness |
| `/api/v1/metrics` | GET | 200 with Prometheus text exposition | Prometheus scrape |

Health behavior is intentional. On `SIGTERM`, the FastAPI lifespan
flips a `_shutting_down` flag (`api/server.py:80-81`); the next
`/health` returns `{"ok": false, "shutting_down": true}` with a 503,
giving load balancers a window to stop sending new traffic before the
container exits. See `api/server.py:580-591`.

`/api/v1/metrics` refreshes the active-runs and SSE-subscribers
gauges on every scrape (`api/server.py:593-609`); counters and
histograms are updated at their call sites. Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: plato-dashboard
    metrics_path: /api/v1/metrics
    static_configs:
      - targets: ['plato.internal:7878']
    scrape_interval: 15s
```

---

## 8. Persistence

Everything that must survive a container restart lives under
`~/.plato/`. Mount that path as a named volume.

```
~/.plato/
├── projects/<uuid>/                  # single-tenant layout
│   ├── meta.json
│   ├── input_files/                  # canonical stage markdown
│   │   ├── data_description.md
│   │   ├── idea.md
│   │   ├── methods.md
│   │   ├── results.md
│   │   ├── literature.md
│   │   ├── referee.md
│   │   ├── plots/
│   │   └── .history/<stage>_<ts>.md  # auto-snapshots
│   ├── paper/                        # main.pdf, main.tex, references.bib
│   │   └── quarkdown/                # rendered HTML+PDF artifacts
│   ├── runs/<run_id>/                # per-run scratch + status.json
│   ├── idea_generation_output/       # cmbagent logs
│   ├── method_generation_output/
│   └── experiment_generation_output/
├── users/<user_id>/                  # multi-tenant layout (auth=1)
│   ├── projects/<uuid>/...           # same as above, namespaced
│   └── keys.json                     # per-user encrypted keys (Wave 4)
└── keys.json                         # single-tenant encrypted keys (mode 0600)
```

The Dockerfile declares `VOLUME ["/root/.plato"]`
(`dashboard/Dockerfile:197`). Without `-v`, all state is lost on
container removal.

In multi-tenant mode (`PLATO_DASHBOARD_AUTH_REQUIRED=1`), the key
store nests under `~/.plato/users/<user_id>/keys.json` — each user
gets their own salt and ciphertext, so a leak of one user's bytes
does not compromise another's.

---

## 9. Backup

The volume is the entire backup surface. Recommended cadence:

- **Hot** (active project): daily.
- **Idle** (no runs in last 7 days): weekly.

Snapshot the volume from a sidecar container so you don't pause the
running app:

```bash
docker run --rm \
  -v plato-data:/data:ro \
  -v "$(pwd)":/backup \
  alpine \
  tar czf "/backup/plato-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" \
    --exclude='*/runs/*/tmp' \
    --exclude='*.qd' \
    --exclude='*/runs/*/log' \
    -C /data .
```

**Exclude**:

- `runs/*/tmp/` — transient scratch.
- `runs/*/log/` — re-derivable from event history, can be huge.
- `*.qd` — Quarkdown intermediate output; regenerated on next render.
- `__pycache__/` if any leak through.

**Include**:

- `meta.json`, `input_files/`, `paper/`, `runs/*/status.json`,
  `runs/*/manifest.json`, `keys.json`, `users/*/keys.json`.

For S3-backed offsite storage, pipe `tar c | aws s3 cp - s3://...` —
no need to materialize the archive on disk.

---

## 10. Restore

Stop the container, restore into the volume, restart:

```bash
docker stop plato-dashboard

docker run --rm \
  -v plato-data:/data \
  -v "$(pwd)":/backup \
  alpine \
  sh -c 'cd /data && rm -rf ./* && tar xzf /backup/plato-20260504T0000Z.tar.gz'

docker start plato-dashboard
```

**Schema-version compatibility.** Project layout is stable across 0.x
patch releases (key store format and `meta.json` shape are versioned).
Restoring a 0.2.x backup into a 0.3+ image may require a one-shot
migration — check the dashboard's
[`CHANGELOG.md`](../dashboard/CHANGELOG.md) "Migration" notes for the
target version before restoring across a minor bump. The
recover-orphaned-runs sweep on startup
(`api/server.py:_recover_orphaned_runs_inline`) marks any
queued/running runs from the backup as `failed` with
`crashed_before_restart` — use the resume endpoint to restart them.

---

## 11. Upgrades

Standard rolling upgrade:

```bash
NEW_TAG=v0.3.0
docker pull plato-dashboard:${NEW_TAG}        # or rebuild from source
docker stop plato-dashboard
docker rm   plato-dashboard
docker run -d \
  --name plato-dashboard \
  --restart unless-stopped \
  -p 7878:7878 \
  -v plato-data:/root/.plato \
  --env-file .env \
  plato-dashboard:${NEW_TAG}
```

The volume persists across the swap. On boot the new container will
sweep any runs that were `queued`/`running` at shutdown and mark
them `failed` so they can be resumed cleanly.

### Breaking-change checklist

Before upgrading, scan
[`dashboard/CHANGELOG.md`](../dashboard/CHANGELOG.md) for the target
version and confirm:

- [ ] Removed/renamed env vars (e.g. `PLATO_AUTH` → `PLATO_DASHBOARD_AUTH_REQUIRED` in 0.2).
- [ ] Schema bumps to `meta.json`, `manifest.json`, or `keys.json`.
- [ ] Storage layout changes (e.g. multi-tenant `users/<uid>/`
  namespacing landed in 0.2).
- [ ] Quarkdown version bump → recompute `QUARKDOWN_SHA256` for any
  local rebuilds.
- [ ] New required runtime deps (rare; stick to the pinned image when in doubt).

If any apply, take a fresh backup (§9) before pulling the new image.

---

## 12. Multi-tenant deployment

Flip a single env var:

```bash
docker run -d \
  --name plato-dashboard \
  -e PLATO_DASHBOARD_AUTH_REQUIRED=1 \
  -v plato-data:/root/.plato \
  -p 7878:7878 \
  plato-dashboard:latest
```

What changes:

- **Every request** must carry an `X-Plato-User: <id>` header. The
  reverse proxy upstream of the container is responsible for
  authenticating the user and injecting this header — Plato itself
  does not implement password auth. The header value is validated
  against `[A-Za-z0-9._-]{1,64}` (`auth.py:_USER_ID_RE`), so it can
  be used as a safe path segment.
- **Project storage** namespaces under
  `~/.plato/users/<user_id>/projects/`.
- **Key store** namespaces under
  `~/.plato/users/<user_id>/keys.json` (Wave 4). Each user's keys
  are encrypted with a salt derived from their path, so dumping one
  user's bytes does not compromise another's.
- **Run-tenant enforcement** (`api/server.py:_enforce_run_tenant`)
  blocks any cross-tenant run access with 403 / 404.
- **CSRF** (`middleware/csrf.py`, Wave 5) double-submits a
  `plato_csrf` cookie + `X-CSRF-Token` header on every mutating
  method. The cookie is non-`HttpOnly` by design — the SPA reads it
  and echoes it back. Safe methods skip the check and mint a token
  on the way out so the first SPA navigation bootstraps the value.
  Exempt SSE / health paths if you front this with a non-cookie
  client.

Adversarial coverage: 15 bypass tests in
`tests/safety/test_dashboard_auth_bypass.py` lock down tenant
boundaries.

---

## 13. Observability

### Structured logs

```bash
-e PLATO_OBS_JSON_LOGS=1
```

Every log line becomes a JSON object: `{"ts": ..., "level": ...,
"logger": ..., "msg": ..., "request_id": ...}`. Pipe stdout into Loki,
Datadog, CloudWatch, or any collector that expects line-delimited JSON.
Off by default to keep dev logs readable.

### Prometheus metrics

Scrape `/api/v1/metrics`. Exposed series include:

- `plato_active_runs` (gauge) — currently running stage workers.
- `plato_sse_subscribers` (gauge) — connected SSE clients.
- `plato_run_duration_seconds` (histogram) — per-stage runtime.
- `plato_llm_tokens_total{provider, model, kind}` (counter) — token usage.
- `plato_llm_cost_usd_total{provider, model}` (counter) — dollar usage.

### Sentry

```bash
-e SENTRY_DSN=https://...@sentry.io/...
```

Wired in `api/server.py:388`. Requires `sentry-sdk` to be installed
in the runtime — it isn't in the pinned image by default; rebuild
with `pip install sentry-sdk` added to the Python install layer if
you need it.

### Langfuse

Set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` (and
`LANGFUSE_HOST` for self-hosted). LLM traces ship automatically.

---

## 14. Common issues

### Quarkdown build failure: sha256 mismatch

```
sha256sum: WARNING: 1 computed checksum did NOT match
```

You either forgot `--build-arg QUARKDOWN_SHA256=...` or pinned a
stale digest. Recompute (§3) and retry. Do **not** "fix" this by
disabling the check — that throws away the supply-chain guarantee.

### LaTeX / Quarkdown timeout on paper render

Large papers + first-time font cache rebuilds can blow past the
default render timeout. Quarkdown's wrapper
(`dashboard/backend/src/plato_dashboard/render/quarkdown.py:23`)
defaults to 90 s per render — there's no env var override today, so
either bump the constant in source or pre-warm the font cache by
running a trivial render in the container before exposing it (this
is the cheaper option for production). xelatex's first-run
`fontconfig` build can take ~30 s on a cold container.

### SSE disconnects under a reverse proxy

nginx and many cloud LBs idle-time SSE streams to death.

- nginx: `proxy_read_timeout 3600s; proxy_buffering off;`
- Caddy: SSE works out of the box — just make sure no `transport.timeouts`
  are tighter than your longest stage.
- AWS ALB: bump idle timeout to 3600 s; the default is 60.
- Cloud Run: SSE is supported; set the request timeout to 3600 s.

### Permission errors on `~/.plato`

Symptom: `PermissionError: [Errno 13]` on first request, or `keys.json`
write fails.

The container runs as root and writes to `/root/.plato`. If you mount
a host directory instead of a named volume, ensure the host owner
matches uid 0 inside the container, or chown after mounting:

```bash
docker run --rm -v "$(pwd)/plato-data:/root/.plato" alpine chown -R 0:0 /root/.plato
```

Named volumes (recommended) have no host-uid coupling and avoid this
entirely.

### Healthcheck flapping at boot

If `docker ps` shows `unhealthy` for the first 30 s after startup,
that is expected — `quarkdown --version` cold-starts the JVM. The
healthcheck has `--start-period=30s` (`dashboard/Dockerfile:204`) and
will turn `healthy` once the JVM warms.

---

## 15. Rollback

Tag every release. To roll back, swap the tag and recycle the
container — the volume preserves state across the swap:

```bash
PREV_TAG=v0.1.7
docker stop plato-dashboard && docker rm plato-dashboard
docker run -d \
  --name plato-dashboard \
  --restart unless-stopped \
  -p 7878:7878 \
  -v plato-data:/root/.plato \
  --env-file .env \
  plato-dashboard:${PREV_TAG}
```

If the rollback crosses a minor version (e.g. 0.3 → 0.2), restore the
last-known-good backup taken before the upgrade (§10). Newer-version
schema bumps may not be readable by the older binary, and the
recover-orphaned-runs sweep at boot will mark any in-flight work as
`failed` — resume them via the `/runs/<id>/resume` endpoint once the
older container is healthy.

For zero-downtime rollback, run the previous-tag container on a
sidecar port (e.g. `:7879`) pointed at a **separate** volume
restored from the pre-upgrade backup, flip the proxy upstream, then
retire the broken container. This avoids the cross-version schema
question entirely at the cost of one extra hot copy of the data.
