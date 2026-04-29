# Contributing to the Plato Dashboard

Thanks for considering a contribution. The dashboard lives at `dashboard/`
inside the [Plato](https://github.com/AstroPilot-AI/Plato) monorepo and ships
as a separate Python package (`plato-dashboard`) plus a Next.js frontend.

This guide covers local setup, the test loop, code style, commit conventions,
and the design-token discipline that keeps the Linear theme cohesive.

## Setup

The backend and frontend are developed side-by-side but installed
independently.

```bash
# 1. Backend — Python 3.13 venv with both plato-dashboard and Plato itself
cd dashboard
python3.13 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -e backend/ -e ../..

# 2. Pin mistralai < 2.0 (see "Plato library install caveat" below)
pip install "mistralai<2.0"

# 3. Frontend
cd frontend
npm install
```

Plato itself must be installed in the *same* venv as `plato-dashboard`,
because the run-manager spawns a Python subprocess that does `from plato
import Plato`. If only one of them is installed the worker will crash on
boot with `ModuleNotFoundError`.

## Run dev

```bash
# From dashboard/
bash scripts/dev.sh
```

`scripts/dev.sh` boots the FastAPI backend on `http://127.0.0.1:7878` and
the Next.js frontend on `http://localhost:3000`. The frontend auto-detects
the backend; if it is down, the UI falls back to a static sample dataset so
the design is demoable as a static page.

To launch from the parent Plato CLI instead:

```bash
plato dashboard            # default port 7878, opens browser
plato dashboard --demo     # PLATO_DEMO_MODE=enabled
plato dashboard --port 7879 --no-browser
```

## Testing

All three test suites must pass before you open a PR. CI enforces them via
`.github/workflows/dashboard-{backend,frontend,build}.yml`.

```bash
# Backend — 32 pytest cases
cd dashboard/backend
source .venv/bin/activate
pytest tests/

# Frontend type-check
cd dashboard/frontend
npx tsc --noEmit

# Frontend end-to-end (Playwright, 6 specs)
npx playwright test
# Or just the smoke spec
npx playwright test smoke.spec.ts
```

When you add a backend route, add a pytest case under
`backend/tests/`. When you add or restyle a stage view, add or update a
Playwright spec under `frontend/tests/`.

## Code style

### TypeScript

- `npx tsc --noEmit` must pass. No `any`, no `// @ts-expect-error` without
  a one-line justification.
- Prefer Server Components by default; mark Client Components with
  `"use client"` only when the file actually needs hooks or browser APIs.
- React components use named exports and PascalCase filenames. Hooks use
  `use-kebab-case.ts` and the `use*` function-name prefix.

### Python

- f-strings everywhere; no `%`-formatting or `.format()`.
- Full type hints on public functions, including `Pydantic` models for
  every wire-shape.
- No comments unless the *why* is non-obvious. The code should explain the
  *what*; comments justify trade-offs and surprises only.
- Pydantic v2 idioms (`model_config`, `Field`) — no v1 holdovers.

### Tailwind v4 + design tokens

- Tailwind v4 utilities only. No inline `style={{ }}` for color, spacing,
  or typography unless a token is genuinely missing (in which case open a
  separate PR to add the token first).
- **No hardcoded hex colors.** The Super Design pre-commit hooks block
  them. Reference design tokens from `frontend/src/app/globals.css`
  instead — e.g. `bg-canvas`, `text-fg-secondary`, `border-border-subtle`.
- New shadow, radius, easing values: add to `globals.css` `@theme`, then
  document the token in `dashboard/DESIGN.md`.

## Commit conventions

Plato Dashboard uses [Conventional Commits](https://www.conventionalcommits.org/).

```
feat: add /costs route with cross-project ledger
fix: kill process group on cancel so cmbagent grandchild dies
chore: bump next from 15.x to 15.y
docs: clarify mistralai pin in dashboard/CONTRIBUTING.md
test: cover capability middleware 403 path
refactor: extract SSE bus into events/bus.py
```

Scope is optional but encouraged for monorepo clarity:
`feat(backend):`, `fix(frontend):`, `chore(ci):`.

## Pull requests

Use the dashboard PR template at
[`.github/PULL_REQUEST_TEMPLATE/dashboard.md`](../.github/PULL_REQUEST_TEMPLATE/dashboard.md).

GitHub does not auto-select alternate templates, so append
`?template=dashboard.md` to the PR-create URL, or paste the template
contents into the description manually.

A good PR:

- Targets `main`.
- Has a Conventional Commit-styled title.
- Links the related issue.
- Includes a "Test plan" checklist.
- Updates `CHANGELOG.md` under `[Unreleased]` if the change is user-facing.

## Linear design discipline

Every visual choice in the dashboard traces back to a token defined in
`dashboard/DESIGN.md`, which mirrors Linear's published tokens via the
[Super Design](https://github.com/Eldergenix/SUPER-DESIGN) skill.

Adding a new color requires **both** of:

1. A `DESIGN.md` token entry — name, hex, semantic role, light/dark variants.
2. A matching mapping in `frontend/src/app/globals.css` under `@theme` so
   Tailwind exposes it as a utility class.

Do not introduce a one-off color directly in a component. The pre-commit
hooks catch hex literals; the design review catches semantically-misused
tokens. If you need a new role (e.g. "warning-subtle"), propose it in the
PR description with a rendered swatch.

## Plato library install caveat

`cmbagent.ocr` imports v1-style `DocumentURLChunk` from `mistralai`, which
v2 of the SDK removed. If you `pip install plato` against a fresh
environment, mistralai will resolve to a v2 release and `from plato.plato
import Plato` will raise `ImportError` on first call — which silently
breaks the dashboard's worker subprocess.

The fix is documented in [Setup](#setup) above:

```bash
pip install "mistralai<2.0"
```

We pin this in `backend/pyproject.toml` for the published `plato-dashboard`
package, but local editable installs need the manual pin until upstream
cmbagent migrates to mistralai v2.

## Reporting issues

File issues against the parent
[AstroPilot-AI/Plato](https://github.com/AstroPilot-AI/Plato/issues) repo
with a `dashboard:` prefix in the title. Include:

- The dashboard version (`pip show plato-dashboard | grep Version`).
- The Plato version (`pip show plato | grep Version`).
- Backend logs from `~/.plato/logs/` if relevant.
- Browser + OS for frontend issues.

Thanks again — looking forward to your contribution.
