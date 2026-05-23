# Deploying Plato Dashboard to Railway

Railway runs the **same single-container image** the dashboard ships to
HuggingFace Spaces with (`dashboard/spaces/Dockerfile`). The image runs
Next.js as the public process on Railway's injected `$PORT`, while the
FastAPI backend runs on localhost and receives `/api/v1` traffic through
the Next proxy. One Railway service hosts the whole app. No separate
frontend service is needed. Production deployments can use a Railway Redis
database by setting `PLATO_REDIS_URL` and `PLATO_USE_FAKEREDIS=false`; when
`PLATO_REDIS_URL` is absent the image can still run with fakeredis or its
bundled local Redis fallback. The research-publication feed
does need Postgres for durable posts, comments, likes, shares, author
tags, and RSS items; without `DATABASE_URL` or
`PLATO_PUBLICATIONS_DATABASE_URL`, publications fall back to a local
SQLite file that is not safe for production deploys.

The repo's [`railway.json`](../railway.json) at the root tells Railway
which Dockerfile to use and where the healthcheck lives — Railway picks
that up automatically when you point a service at this repo.

## What you get

- **Public URL** at `https://<service>-<hash>.up.railway.app`
- **Demo mode on by default**: code-execution stages locked, hard
  $-budget cap per session, projects auto-cleaned after 30 min idle
  (this is the safe posture for a public demo — don't disable it
  without auth in front)
- **Healthcheck** at `/api/v1/health` (Railway will roll back failed
  deploys automatically)

---

## Deploy in three steps (web UI)

1. **New project**
   - Go to [railway.com/new](https://railway.com/new) → **Deploy from GitHub repo**
   - Pick `Eldergenix/Plato-Scientific-Research-Autonomous-Agent`
   - Railway reads `railway.json`, finds `dashboard/spaces/Dockerfile`,
     starts building. First build takes **~6–10 minutes** (cmbagent +
     LangChain + LaTeX install dominate).

2. **Add Postgres for the publication feed**

   Add a Postgres database service in the same Railway project. Then set
   the app service variables to reference that database:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `PLATO_PUBLICATIONS_DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |

   `PLATO_PUBLICATIONS_DATABASE_URL` is read first by the publication
   store, while `DATABASE_URL` keeps the deployment compatible with
   standard Railway/Postgres conventions.

3. **Set environment variables** (Service → **Variables** tab)

   At least one LLM provider key is required for the demo to actually
   generate anything. `ANTHROPIC_API_KEY` is the safest single choice
   because Plato defaults to Claude for the orchestration agents.

   | Variable | Required? | Notes |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | recommended | `sk-ant-...` |
   | `OPENAI_API_KEY` | optional | only if you want users to pick GPT models |
   | `GOOGLE_API_KEY` | optional | only if you want Gemini models |
   | `PLATO_DEMO_MODE` | leave unset | defaults to `enabled` from the Dockerfile; only override to `disabled` if you've put auth in front |
   | `PLATO_BACKEND_PORT` | leave unset | defaults to `7878`; FastAPI listens here inside the container |
   | `PLATO_AUTH` | optional | set to `enabled` + `PLATO_AUTH_TOKEN=...` to gate the dashboard behind a bearer cookie |
   | `PLATO_REDIS_URL` | recommended for production | `${{Redis.REDIS_URL}}` from a Railway Redis database |
   | `PLATO_USE_FAKEREDIS` | recommended for production | set `false` when `PLATO_REDIS_URL` points at Railway Redis |
   | `DATABASE_URL` | required for publications | `${{Postgres.DATABASE_URL}}` from the Railway Postgres service |
   | `PLATO_PUBLICATIONS_DATABASE_URL` | required for publications | same value; publication store reads this before `DATABASE_URL` |

   Do **not** set `PORT` yourself — Railway injects it.

   For the hosted SaaS/Lab deployment, add this Clerk and proxy contract
   before deploying a build that has `NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk`.
   The dashboard intentionally fails closed when Clerk auth is requested but
   these values are missing or invalid.

   | Variable | Required? | Notes |
   |---|---|---|
   | `NEXT_PUBLIC_PLATO_AUTH_PROVIDER` | required for hosted SaaS | set to `clerk` |
   | `PLATO_AUTH_PROVIDER` | required for hosted SaaS | set to `clerk` |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | required for hosted SaaS | Clerk publishable key for this domain |
   | `CLERK_SECRET_KEY` | required for hosted SaaS | Clerk secret key for server-side auth |
   | `PLATO_BACKEND_PROXY_SECRET` | recommended for hosted SaaS | 32+ random characters shared by Next.js and FastAPI; protects private tenant headers. In the single-service image, this can be omitted when both runtimes share `CLERK_SECRET_KEY`, because they derive the internal proxy secret from it. |
   | `PLATO_PUBLIC_ORIGIN` | required for production readiness | canonical HTTPS app origin, for example `https://discovering.app` |
   | `NEXT_PUBLIC_CLERK_PROXY_URL` | required for production readiness | usually `${PLATO_PUBLIC_ORIGIN}/__clerk` |
   | `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | recommended | `/sign-in` |
   | `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | recommended | `/sign-up` |
   | `NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL` | recommended | `/` |
   | `NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL` | recommended | `/` |
   | `NEXT_PUBLIC_PLATO_HOSTED_BILLING` | required for Clerk Billing UI | set to `enabled` only after Clerk Billing is configured |
   | `PLATO_HOSTED_TRIAL_PUBLICATIONS_PER_WEEK` | optional | defaults to `2` |
   | `PLATO_HOSTED_USER_PRO_FEE_CENTS` | optional | defaults to `1499` |
   | `PLATO_HOSTED_USER_RESEARCHER_FEE_CENTS` | optional | defaults to `9999` |
   | `PLATO_HOSTED_LAB_BASE_FEE_CENTS` | optional | defaults to `9900` |
   | `PLATO_HOSTED_LAB_SEAT_FEE_CENTS` | optional | defaults to `0` |

   Use `railway variables --skip-deploys --set ...` when adding missing
   hosted variables during a release-prep pass; then trigger a single
   deployment after the variable set is complete.

   Before deploying hosted SaaS/Lab mode, run the local source gates and
   redacted strict preflight from the repo root:

   ```bash
   bash dashboard/scripts/check-local-production-gates.sh
   bash dashboard/scripts/check-hosted-saas-preflight.sh --railway --service plato --environment production --hosted-required --strict
   ```

   Strict preflight treats warnings as release blockers so hosted production
   cannot ship with missing canonical-origin or billing-readiness flags.

   After a deployment, run the read-only production readiness check. It
   repeats the hosted preflight, probes the public health/auth boundary, and
   scans the latest Railway build/deploy logs for warning and error markers:

   ```bash
   bash dashboard/scripts/check-production-readiness.sh --service plato --environment production --origin https://discovering.app
   ```

   If the Railway CLI variable endpoint is unavailable during verification,
   provide a local JSON or KV variables snapshot with `--variables-file`. The
   readiness script still redacts secret values and reports only key
   presence/length:

   ```bash
   bash dashboard/scripts/check-production-readiness.sh --service plato --environment production --origin https://discovering.app --variables-file /path/to/railway-variables.json
   ```

4. **Generate a public domain** (Service → **Settings** → **Networking** →
   **Generate Domain**). Open the URL. The first request after a cold
   start can take ~10s while the Python process imports the world.

---

## Deploy via CLI (alternative)

If you'd rather drive it from your laptop:

```bash
# one-time
railway login
railway link            # pick or create the project

# one-time production variables
railway add --database postgres
railway add --database redis
railway variables --service plato --set 'DATABASE_URL=${{Postgres.DATABASE_URL}}'
railway variables --service plato --set 'PLATO_PUBLICATIONS_DATABASE_URL=${{Postgres.DATABASE_URL}}'
railway variables --service plato --set 'PLATO_REDIS_URL=${{Redis.REDIS_URL}}'
railway variables --service plato --set 'PLATO_USE_FAKEREDIS=false'
railway variables --service plato --set ANTHROPIC_API_KEY=sk-ant-...

# hosted SaaS/Lab variables, if this service uses Clerk
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_PLATO_AUTH_PROVIDER=clerk'
railway variables --service plato --skip-deploys --set 'PLATO_AUTH_PROVIDER=clerk'
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...'
railway variables --service plato --skip-deploys --set 'CLERK_SECRET_KEY=sk_...'
railway variables --service plato --skip-deploys --set 'PLATO_BACKEND_PROXY_SECRET=<32+ random chars>'
railway variables --service plato --skip-deploys --set 'PLATO_PUBLIC_ORIGIN=https://discovering.app'
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_CLERK_PROXY_URL=https://discovering.app/__clerk'
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in'
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up'
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=/'
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=/'
railway variables --service plato --skip-deploys --set 'NEXT_PUBLIC_PLATO_HOSTED_BILLING=enabled'

# PLATO_BACKEND_PROXY_SECRET remains the explicit split-service contract.
# The default Railway image runs Next.js and FastAPI in one service, so both
# runtimes can derive the same private backend proxy secret from CLERK_SECRET_KEY
# when the explicit variable is absent.

bash dashboard/scripts/check-local-production-gates.sh
bash dashboard/scripts/check-hosted-saas-preflight.sh --railway --service plato --environment production --hosted-required --strict

# every deploy after that
railway up              # builds + deploys from current branch
railway domain          # creates and prints the public URL
bash dashboard/scripts/check-production-readiness.sh --service plato --environment production --origin https://discovering.app
# If Railway variable reads fail, use --variables-file /path/to/railway-variables.json
```

`railway up` from the repo root will pick up `railway.json`
automatically — no need to pass `-d dashboard/spaces/Dockerfile`.

---

## Persistence (optional)

Project artifacts still live on the container filesystem. By default the
container's project state lives at
`/home/plato/.plato/projects` and is **wiped every redeploy**. That's
fine for a stateless demo, but if you want runs to survive across
deploys:

1. Service → **Settings** → **Volumes** → **New Volume**
2. **Mount Path**: `/home/plato/.plato/projects`
3. **Size**: 1 GB is plenty for demo traffic; bump if real research happens here

The `30-min idle cleanup` in demo mode still runs over the volume, so
you won't fill it up unattended.

Publication feed data is separate from project artifacts. Posts,
comments, likes, shares, author tags, and RSS metadata are stored in
Postgres when `PLATO_PUBLICATIONS_DATABASE_URL` or `DATABASE_URL` is set.
The app creates the `publications`, `publication_comments`,
`publication_likes`, and `publication_shares` tables idempotently on
startup or first feed access.

---

## Cost estimate

Railway bills on actual CPU + RAM + egress. With demo mode on and
fakeredis (no companion services):

- **Idle**: ~$0.50–1.00 / month (container running, no traffic)
- **Light demo traffic** (a few sessions / day): **~$5 / month**
- **Heavy LLM usage**: dominated by your provider bills (Anthropic /
  OpenAI / Google), not Railway

The image is ~1.7 GB on disk, which fits Railway's free / hobby tier
limits comfortably.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Build times out at ~10 min | First build is slow; cmbagent compile | Re-run; subsequent builds use the layer cache |
| `Healthcheck failed: /api/v1/health` after green build | App still booting (LangChain imports) | Bump `healthcheckTimeout` in `railway.json` to `600` |
| `502 Bad Gateway` on first request | Cold start or Next waiting for FastAPI | Wait ~10s, refresh; then check `railway logs` if it persists |
| `{"message":"Application not found"}` on dashboard routes | Public domain is not attached to the `plato` service, or the service has no active deployment | Reconnect the domain to the `plato` service, confirm the active production deployment, or redeploy from the repo root with `railway up` |
| `Error: spawn npm ENOENT` during boot | Runtime pruned TypeScript while `next.config.ts` still needs it | Keep the built frontend `node_modules` from the builder stage; do not run `npm prune --omit=dev` unless the config is compiled or converted |
| `"No models configured"` in the UI | Forgot to set provider keys | Set `ANTHROPIC_API_KEY` (or another) in Variables → Redeploy |
| Demo mode banner won't go away | `PLATO_DEMO_MODE=enabled` is the default | Set `PLATO_DEMO_MODE=disabled` **only if you've also enabled `PLATO_AUTH`** |
| Publication feed resets after redeploy | App fell back to local SQLite | Add Railway Postgres and set `PLATO_PUBLICATIONS_DATABASE_URL=${{Postgres.DATABASE_URL}}` on the app service |
| `postgres.railway.internal` does not resolve from `railway run` on your laptop | Railway private networking only resolves inside Railway services | Verify with a deployed service, or use the Postgres `DATABASE_PUBLIC_URL` only for local one-off database checks |

---

## Why one container, not two services?

The repo's [`dashboard/Dockerfile`](Dockerfile) and
[`dashboard/spaces/Dockerfile`](spaces/Dockerfile) are multi-stage builds.
The builder runs `next build`, then the runtime image starts two local
processes under `tini`:

1. FastAPI on `PLATO_BACKEND_PORT` for `/api/v1`
2. Next.js on Railway's public `$PORT`

This avoids static-export limitations around dynamic run pages and the
Next API proxy, while still keeping operations simple:

- **One origin** → zero CORS, zero proxy config
- **One service** → simpler env vars, no internal-DNS plumbing
- **One restart unit** → consistent state on cold starts

If you ever want to scale frontend and backend independently (different
CDN, different region), the split-service pattern is straightforward:
deploy `dashboard/frontend/` as a Next.js service (Nixpacks auto-detects)
and `dashboard/backend/` as a Python service, then point
`NEXT_PUBLIC_API_BASE` at the backend's internal Railway URL. But you
won't need that for a demo.
