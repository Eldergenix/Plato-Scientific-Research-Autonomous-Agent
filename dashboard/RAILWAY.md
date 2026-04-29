# Deploying Plato Dashboard to Railway

Railway runs the **same single-container image** the dashboard ships to
HuggingFace Spaces with (`dashboard/spaces/Dockerfile`). The image embeds
the statically-exported Next.js frontend inside the FastAPI gateway, so
one Railway service hosts the whole app. No separate frontend service,
no Redis, no Postgres needed.

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

2. **Set environment variables** (Service → **Variables** tab)

   At least one LLM provider key is required for the demo to actually
   generate anything. `ANTHROPIC_API_KEY` is the safest single choice
   because Plato defaults to Claude for the orchestration agents.

   | Variable | Required? | Notes |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | recommended | `sk-ant-...` |
   | `OPENAI_API_KEY` | optional | only if you want users to pick GPT models |
   | `GOOGLE_API_KEY` | optional | only if you want Gemini models |
   | `PLATO_DEMO_MODE` | leave unset | defaults to `enabled` from the Dockerfile — only override to `disabled` if you've put auth in front |
   | `PLATO_AUTH` | optional | set to `enabled` + `PLATO_AUTH_TOKEN=...` to gate the dashboard behind a bearer cookie |
   | `PLATO_USE_FAKEREDIS` | leave unset | already `true` in the Dockerfile; no Redis service needed |

   Do **not** set `PORT` yourself — Railway injects it.

3. **Generate a public domain** (Service → **Settings** → **Networking** →
   **Generate Domain**). Open the URL. The first request after a cold
   start can take ~10s while the Python process imports the world.

---

## Deploy via CLI (alternative)

If you'd rather drive it from your laptop:

```bash
# one-time
railway login
railway link            # pick or create the project

# every deploy after that
railway up              # builds + deploys from current branch
railway variables --set ANTHROPIC_API_KEY=sk-ant-...
railway domain          # creates and prints the public URL
railway logs            # tail
```

`railway up` from the repo root will pick up `railway.json`
automatically — no need to pass `-d dashboard/spaces/Dockerfile`.

---

## Persistence (optional)

By default the container's project state lives at
`/home/plato/.plato/projects` and is **wiped every redeploy**. That's
fine for a stateless demo, but if you want runs to survive across
deploys:

1. Service → **Settings** → **Volumes** → **New Volume**
2. **Mount Path**: `/home/plato/.plato/projects`
3. **Size**: 1 GB is plenty for demo traffic; bump if real research happens here

The `30-min idle cleanup` in demo mode still runs over the volume, so
you won't fill it up unattended.

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
| `502 Bad Gateway` on first request | Cold start | Wait ~10s, refresh — happens once per idle-restart |
| `"No models configured"` in the UI | Forgot to set provider keys | Set `ANTHROPIC_API_KEY` (or another) in Variables → Redeploy |
| Demo mode banner won't go away | `PLATO_DEMO_MODE=enabled` is the default | Set `PLATO_DEMO_MODE=disabled` **only if you've also enabled `PLATO_AUTH`** |

---

## Why one container, not two services?

The repo's [`dashboard/Dockerfile`](Dockerfile) is a multi-stage build
that runs `next build --turbopack` with `output: "export"` to produce a
pure-static `out/` directory, then copies that into the Python image
where FastAPI serves it at `/`. The frontend has no Node runtime in
production — it's just HTML + JS files served by uvicorn. So:

- **One origin** → zero CORS, zero proxy config
- **One service** → simpler env vars, no internal-DNS plumbing
- **One restart unit** → consistent state on cold starts

If you ever want to scale frontend and backend independently (different
CDN, different region), the split-service pattern is straightforward:
deploy `dashboard/frontend/` as a Next.js service (Nixpacks auto-detects)
and `dashboard/backend/` as a Python service, then point
`NEXT_PUBLIC_API_BASE` at the backend's internal Railway URL. But you
won't need that for a demo.
