# Plato autonomous scientist on Cloudflare (jarvisos.xyz)

```
browser ──▶ Worker (jarvisos.xyz)
             ├─ /            static UI (Workers Static Assets)
             ├─ GET /api/*   reads ──▶ Hyperdrive ──▶ Supabase Postgres (schema `plato`)
             ├─ POST /api/*  ──▶ Container "campaign-<id>" (Python: LangGraph swarm + sandbox)
             │                     └─▶ Supabase Postgres (session pooler) + Claude Haiku 5.5
             └─ cron */5     re-sends /run for every unfinished campaign (crash/evict resume)
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
3. Deploys the Worker and Container.
4. Sets the secrets.
5. Smoke-tests `https://jarvisos.xyz/api/health`.

It prints the generated API token once. Use the **session** pooler (port 5432), not the
transaction pooler (6543): runs hold session-level advisory locks.

## Local development

```bash
npm ci
CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE='postgresql://postgres:pw@127.0.0.1:5432/postgres' \
  npx wrangler dev --enable-containers=false --var PLATO_API_TOKEN:dev --var PLATO_INTERNAL_TOKEN:dev
npm run check   # TypeScript
```

The Python service runs on its own: `PLATO_DATABASE_URL=... PLATO_INTERNAL_TOKEN=... python -m plato.scientist.service`.
