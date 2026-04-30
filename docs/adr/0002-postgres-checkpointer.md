# ADR 0002 — Postgres checkpointer is opt-in for multi-tenant deployments

- **Status**: Accepted
- **Date**: 2026-04-29
- **Deciders**: Plato maintainers
- **Phase**: 5 (Production hardening)

## Context

`plato.state.make_checkpointer` supports three LangGraph checkpoint
backends: `memory`, `sqlite`, and `postgres`. The factory has shipped
since Phase 1, but until now only the SQLite branch had an integration
test (`tests/integration/test_checkpoint_resume.py`). The Postgres
branch was effectively unverified — the factory existed, but nothing in
CI exercised it against a real server.

We want a clear answer to two operational questions:

1. **When should an operator pick `postgres` over `sqlite`?**
2. **What is the cost of keeping the postgres path supported?**

## Decision

1. **Default backend stays SQLite.** A single-user CLI run, a developer
   laptop, and the eval harness all use `make_checkpointer("sqlite")`,
   which writes to `~/.plato/state.db`. No external service is required.

2. **Postgres is opt-in for multi-tenant or dashboard deployments.**
   Use `make_checkpointer("postgres", dsn=...)` when:

   - Multiple long-running graph processes need to read/write the same
     checkpoint history concurrently (e.g. the dashboard backend plus a
     worker pool).
   - Operations needs centralized backups, point-in-time recovery, or
     row-level audit independent of the application host.
   - You are running on Railway/Fly/Kubernetes where local disk on the
     application container is ephemeral and SQLite-on-volume is awkward.

   For a single-user CLI run, SQLite is strictly simpler and faster.

3. **`langgraph-checkpoint-postgres` stays out of `pyproject.toml`.**
   The extra is loaded lazily; it falls back to `MemorySaver` with a
   `RuntimeWarning` when missing. CI installs it on demand in the
   `integration-postgres` workflow. Adding it to the base install would
   pull `psycopg` and its native deps onto every developer's machine
   for a feature 95% of users will not use.

4. **Coverage is enforced by a nightly integration job.** The
   `.github/workflows/integration-postgres.yml` workflow stands up
   `postgres:16` as a service container, installs the extra, and runs
   `tests/integration/test_postgres_checkpointer.py`. The local
   equivalent is `docker/docker-compose.test.yml`. Both pin the same
   image and credentials so failures reproduce 1:1.

## Consequences

**Positive**

- Operators get a tested, supported path to durable multi-tenant state
  without paying the dependency cost on every install.
- The factory contract (lazy import, fallback warning, identical
  `BaseCheckpointSaver` interface) is now actually verified end-to-end,
  not just at import time.
- Future regressions in the upstream `langgraph-checkpoint-postgres`
  package are caught nightly instead of in production.

**Negative**

- One more nightly CI job to monitor.
- Docs now have to spell out the SQLite-vs-Postgres choice, or users
  will pick wrong defaults.

**Neutral**

- `pyproject.toml` is unchanged; the dependency surface for the default
  install is identical to Phase 4.

## References

- Factory: [plato/state/checkpointer.py](../../plato/state/checkpointer.py)
- SQLite resume test: [tests/integration/test_checkpoint_resume.py](../../tests/integration/test_checkpoint_resume.py)
- Postgres resume test: [tests/integration/test_postgres_checkpointer.py](../../tests/integration/test_postgres_checkpointer.py)
- Compose file: [docker/docker-compose.test.yml](../../docker/docker-compose.test.yml)
- Nightly CI: [.github/workflows/integration-postgres.yml](../../.github/workflows/integration-postgres.yml)
- ADR 0001: [0001-langgraph-as-default-backend.md](0001-langgraph-as-default-backend.md)
