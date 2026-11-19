# Plato autonomous scientist on Cloudflare (jarvisos.xyz)

```
browser ──▶ Worker (jarvisos.xyz)
             ├─ /                 static UI (Workers Static Assets)
             ├─ /api/auth, /api/me accounts and sessions (HttpOnly cookie) ──▶ Hyperdrive ──▶ Postgres
             ├─ GET /api/*        reads ──▶ Hyperdrive ──▶ Supabase Postgres (schema `plato`)
             ├─ /api/projects/*   ──▶ Durable Object "ProjectAgent" (Claude Opus 5.5 orchestrator;
             │                        its tools start research threads = campaigns)
             ├─ POST /api/campaigns ──▶ Container "campaign-<id>" (Python: LangGraph swarm + sandbox)
             │                          └─▶ Supabase Postgres (session pooler) + Claude Haiku 5.5
             └─ cron */5          resumes unfinished campaigns, clears expired sessions, unsticks agents
```

Why this shape:

* **Container, not a Worker, runs the swarm.** A campaign runs for minutes to hours,
  executes model-written Python in a Linux sandbox (namespaces, rlimits, `setpriv`)
  and needs numpy/scipy/matplotlib. Workers are V8 isolates with request-scoped CPU,
  so the Python service runs in one Container instance per campaign (`standard-3`:
  2 vCPU, 8 GiB). Each campaign is isolated from the others, and instances scale with
  the number of campaigns (`max_instances`).
* **Postgres is the durable state, so Queues/Workflows are not needed.** Every step
  (claims with leases, facts, evidence, budgets, campaign status) is committed to the
  dual graph. A restarted container resumes from the database, and a session-level
  advisory lock guarantees one runner per campaign.
* **Hyperdrive for Worker reads.** It pools the Worker's connections to Supabase. Query caching is
  disabled so the UI sees live campaign progress.

## Accounts, projects and API keys

* **Sign-up is open.** Passwords are PBKDF2-SHA256 (100k iterations) over an HMAC pepper;
  sessions are random 256-bit tokens in an `HttpOnly; Secure; SameSite=Lax` cookie, stored hashed.
* **Projects** are conversations with an orchestrator agent (a Durable Object per project). It
  starts research threads (campaigns) that run on their own, and checks on them. The ⌘J panel
  asks it questions from any page, with the campaign you're viewing as context.
* **Shared key with a monthly allowance.** Everyone runs on the deploy's `ANTHROPIC_API_KEY` up to
  `PLATO_DEFAULT_MONTHLY_TOKENS` (a var in `wrangler.jsonc`, default 5M) per account per month;
  admins can change each person's allowance in Settings → Members. People can add their own key
  in Settings → API key: it's validated, encrypted with AES-256-GCM, and only its last four
  characters are ever shown. Own-key work isn't counted against the allowance.
* **Models per role.** The project agent runs on `PLATO_ORCHESTRATOR_MODEL` (Claude Opus 5.5);
  every sub-agent in a research thread (planner, experiment writer, research engineer, observer,
  figure critic, skeptic, paper writer, reviewers) runs on `PLATO_SCIENTIST_MODEL` (Claude Haiku
  5.5). `PLATO_ROLE_MODELS`, a JSON string such as `{"skeptic": "claude-sonnet-5-5"}`, overrides
  single roles (names in `src/models.json`). A thread keeps the role models it was created with.
  Budgets and the allowance count **allowance tokens**: tokens times the model's price relative
  to Haiku 5.5 (`plato/scientist/models.py`), so an Opus 5.5 token counts 40. This applies to own-key
  work too, so a thread's token budget means the same spend on any model. The project agent
  retries a policy refusal on Anthropic's default fallback model (`fallbacks: "default"`).
* **Admins.** Paste the deploy's `PLATO_API_TOKEN` in Settings → Security & access once to make
  your account an admin. The bearer token also still works for scripts.
* **`PLATO_SECRETS_KEY`** derives the password pepper and the key that encrypts saved API keys.
  The deploy script creates it once, keeps a copy in `~/.config/plato/secrets-key` (mode 600) and
  never replaces it on the Worker: a different key would invalidate every password and saved key.

## Deploy

Prerequisites: Node 22, Docker running, a Cloudflare account that owns the
`jarvisos.xyz` zone (with Workers Paid for Containers), and Python with `asyncpg` for
the migration step.

```bash
export PLATO_DATABASE_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require'
export ANTHROPIC_API_KEY=...
npx wrangler login            # or export CLOUDFLARE_API_TOKEN=...
./scripts/deploy.sh
```

The script:

1. Applies the schema migrations.
2. Creates or reuses the `plato-supabase` Hyperdrive config, with caching disabled.
3. Deploys the Worker, the Container and the `ProjectAgent` Durable Object.
4. Sets the secrets, adding `PLATO_SECRETS_KEY` only if the Worker doesn't have one.
5. Smoke-tests `https://jarvisos.xyz/api/health`, the signed-out `/api/me` and the UI assets.

It prints the generated API token once. Use the **session** pooler (port 5432), not the
transaction pooler (6543): runs hold session-level advisory locks.

## Local development

```bash
npm ci
CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE='postgresql://postgres:pw@127.0.0.1:5432/postgres' \
  npx wrangler dev --enable-containers=false --var PLATO_API_TOKEN:dev --var PLATO_INTERNAL_TOKEN:dev \
    --var PLATO_SECRETS_KEY:"$(openssl rand -base64 32)" --var ANTHROPIC_API_KEY:sk-ant-... \
    --var PLATO_DEV_SERVICE_URL:http://127.0.0.1:8080
npm run check   # TypeScript
```

The Python service runs on its own: `PLATO_DATABASE_URL=... PLATO_INTERNAL_TOKEN=... python -m plato.scientist.service`.
`PLATO_DEV_SERVICE_URL` sends the Worker's container calls to it, and `PLATO_DEV_ANTHROPIC_BASE_URL`
points the agent at a stub of the Messages API. Both are for local development only.

### End-to-end tests (local only)

With wrangler dev on :8787 (`PLATO_DEV_ANTHROPIC_BASE_URL:http://127.0.0.1:8790`, `PLATO_API_TOKEN:dev`)
and the Python service running:

```bash
node e2e/stub-anthropic.mjs /tmp/stub-requests.jsonl &   # scripted stand-in for the Messages API
node e2e/api.test.mjs /tmp/stub-requests.jsonl           # accounts, keys, allowance, projects, agent
node e2e/ui.test.cjs /tmp/plato-ui                        # browser run (Playwright); fails on console errors
```

Both refuse to run against anything but a local URL: they sign up accounts and use the dev admin token.
Sign-up is throttled per IP, so repeated local runs within an hour need `DELETE FROM plato.auth_attempts`.
