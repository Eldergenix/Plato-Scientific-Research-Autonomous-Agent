# Plato Dashboard — Backend

## Overview

FastAPI gateway that wraps Plato's Python class, runs each long-running
stage (`get_idea`, `get_method`, `get_results`, `get_paper`, `referee`) in
a subprocess worker, and streams agent reasoning + token usage to the
frontend over Server-Sent Events. Subprocess (not threads) is intentional:
cmbagent holds its own subprocess for code execution, and only killing the
process group on cancel is reliable.

## Prerequisites

- Python `>=3.12,<3.14` (3.12 recommended; matches root `pyproject.toml`)
- **Optional** Redis — production event bus. For local dev,
  `PLATO_USE_FAKEREDIS=1` falls back to fakeredis with no setup.
- **Optional** Postgres — durable LangGraph checkpoints when
  `PLATO_POSTGRES_DSN` is set. Defaults to SQLite.

## Setup

```bash
# from repo root:
cd "$(git rev-parse --show-toplevel)/dashboard/backend"

python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .

# Plato itself must be importable in the same venv (the worker subprocess
# does `from plato.plato import Plato`). `../..` is the repo root from here.
pip install -e ../..

# See ../README.md for why mistralai must be pinned to <2.0:
pip install "mistralai<2.0"
```

## Run dev server

```bash
uvicorn plato_dashboard.api.server:app --reload --port 7878
```

Or via the installed entry point:

```bash
plato-dashboard-api          # → http://127.0.0.1:7878
```

Health check:

```bash
curl -s http://127.0.0.1:7878/api/v1/health
```

## Environment variables

| Var | Purpose | Default |
|---|---|---|
| `PLATO_PROJECT_ROOT` | Root dir for project artifacts (`<root>/projects/<uuid>/`). | `~/.plato` |
| `PLATO_PORT` | Port for the API server. | `7878` |
| `PLATO_DASHBOARD_AUTH_REQUIRED` | When `1`, the API reads `X-Plato-User` from the upstream proxy and scopes every project / key store / run artifact per tenant. | `0` |
| `PLATO_USE_FAKEREDIS` | When `1`, the in-process fakeredis stand-in replaces a real Redis dependency — handy for local dev and tests. | `0` |
| `PLATO_POSTGRES_DSN` | LangGraph checkpoint store DSN (e.g. `postgresql://user:pw@host/db`). When unset, falls back to SQLite under `PLATO_PROJECT_ROOT`. | unset |
| `PLATO_KEYS_PATH` | Path to the encrypted provider-key store (mode 0600). | `~/.plato/keys.json` |

Demo mode (`PLATO_DEMO_MODE=enabled`) and dashboard auth (`PLATO_AUTH=...`)
are documented in [`../README.md`](../README.md).

## Tests

```bash
pytest
```

The suite runs against fakeredis and ephemeral project dirs by default;
no external services are required.

## Project structure

```
src/plato_dashboard/
├── api/        # FastAPI routes (server.py), capabilities/auth middleware
├── events/     # in-memory + Redis pub/sub bus
├── storage/    # project_store.py (mirrors Plato's project_dir/), key_store.py
├── worker/     # subprocess Plato runner + cancellation + log tail
└── render/     # markdown + plot rendering helpers for stage views
```

See [`../README.md`](../README.md) for the dashboard's overall architecture
and the cross-component request flow.
