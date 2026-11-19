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

## Manuscript tab: peer review and PDF

The **Manuscript** tab shows the paper as text, as a typeset **PDF**, as LaTeX (optionally with
the PDF beside it) and as BibTeX. The PDF is the preprint layout (arXiv profile) built by the
container's pdfLaTeX without a model call (`GET /api/campaigns/:id/manuscript.pdf`); the Worker
keeps it in R2 under `previews/<campaign>/<latex evidence id>.pdf`, so only the first view of a
paper wakes the container.

The **automated peer review** opens in a right panel that closes, reopens and resizes (drag the
edge, arrow keys on it, double-click to reset; width and state are remembered). The handling
editor judges the paper claim by claim: each assessment quotes the manuscript verbatim and gives
a verdict (approved, needs revision, rejected), severity, the evidence with its numbers, the
critique and the fix. When the paper is revised, a second pass re-reads every claim in the
revision (resolved, partly resolved, unresolved, removed) and gives the decision on the paper as
published. Claims are marked in the paper by their final state; clicking a quote jumps to the
sentence and clicking a marked sentence opens its card. The reviewer panel, claim support and
citation checks sit below. Reviews written before claim-by-claim verdicts show their required
changes.

## Publication packages

The **Publish** tab of a finished research thread builds a submission package for one venue:
Nature, Nature Communications, Science, Cell, NEJM, The Lancet, JAMA, Genes (MDPI) or arXiv.
The container builds it (`plato/publish`, pdfLaTeX and pandoc in a sandbox) and the Worker
streams the zip into the `EXPORTS` R2 bucket (`exports/<campaign>/<export>.zip`). Each package has:

* the manuscript as PDF, LaTeX (one self-contained `.tex`), Word and JATS XML (PubMed Central's
  format), laid out to the journal's rules: title and abstract limits, structured abstracts,
  section headings, line numbers, display-item limits, Key Points, Research in Context, keywords;
* references as BibTeX, RIS and CSL JSON, formatted with the journal's official CSL style
  (`plato/publish/csl`, CC BY-SA);
* figures (PDF and 300-dpi PNG with their source data), the Supplementary Information PDF,
  data as CSV and Excel, the experiments' code and logs, the review record, `PROVENANCE.json`,
  `CITATION.cff`, an `arxiv/` folder ready to upload, and `SUBMISSION_CHECKLIST.md`.

The journal rules and their sources are in `plato/publish/journals.py` (`src/journals.json` is
generated from it; a test keeps them equal). The model writes only the front matter (title,
abstract, key points) once per thread and journal, from the manuscript's own facts; a check flags
any number that isn't in the manuscript. Without a model the package still builds. Builds are
byte-reproducible.

Packages download from the tab, preview single files (`/api/exports/:id/file?path=`), go to
Google Drive, Dropbox or OneDrive, by email through Gmail or Outlook (with a signed download
link valid for 7 days and the PDF attached), or into Files.

## Files and connected services

**Files** (Settings → Files) keeps a person's research files in R2 (`library/<account>/<id>`):
uploads up to 25 MiB, imports, email attachments and saved packages. Data files (CSV, Excel, VCF,
FASTA/FASTQ, BAM, Parquet, HDF5, …) become datasets of a new thread, reference files (`.bib`,
`.ris`, `.nbib`, EndNote XML) become citable papers, and documents (PDF, Word, Markdown, LaTeX)
become background the agents read, framed as untrusted text.

**Connected services** (Settings → Connected services) uses [Composio](https://composio.dev):
each person is one Composio user (`plato-<account id>`) and signs in on the service's own page,
so Plato never holds their OAuth tokens. Google Drive, Dropbox and OneDrive can be browsed and
imported from and sent to; Gmail and Outlook send packages. Automatic import: a Drive folder
trigger and a Gmail trigger save new files to Files through a signed webhook
(`/api/integrations/webhook`, Standard Webhooks HMAC, 5-minute replay window, stored once per
delivery id); the cron retries failed imports up to five times.

Secrets: `COMPOSIO_API_KEY` (without it the feature is off) and `COMPOSIO_WEBHOOK_SECRET`, which
`scripts/composio-setup.mjs` creates with the webhook subscription during the deploy.

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

Files, connected services and packages run against a Composio stub. Start wrangler dev with
`--var PLATO_DEV_COMPOSIO_BASE_URL:http://127.0.0.1:8791 --var COMPOSIO_API_KEY:ak_stub
--var COMPOSIO_WEBHOOK_SECRET:<secret> --var PLATO_DEFAULT_MONTHLY_TOKENS:1500000`, and the
Python service with the same database in `PLATO_DATABASE_URL`:

```bash
node e2e/unit.test.mjs                                    # webhook signatures, zip reader (no services)
node e2e/stub-composio.mjs 8791 &                          # Composio API stand-in
COMPOSIO_WEBHOOK_SECRET=<secret> PLATO_DATABASE_URL=... node e2e/integrations.test.mjs
PLATO_DATABASE_URL=... node e2e/publish-ui.test.cjs /tmp/plato-ui
PLATO_DATABASE_URL=... node e2e/review-ui.test.cjs /tmp/plato-ui   # review panel, PDF view (needs pdflatex)
```

All of them refuse to run against anything but a local URL: they sign up accounts and use the dev admin token.
Sign-up is throttled per IP, so repeated local runs within an hour need `DELETE FROM plato.auth_attempts`.
