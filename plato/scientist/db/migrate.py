"""Idempotent, restart-safe schema migrations ("restart equals migrate").

Every process that opens the store calls :func:`migrate`. The function:

* serialises concurrent migrators with a transaction-scoped advisory lock, so N
  containers booting at once apply each migration exactly once;
* records ``(version, sha256)`` in ``plato.schema_migrations`` and refuses to start if
  an applied migration file was edited afterwards (checksum drift);
* applies all pending files inside the locked transaction (one savepoint per
  file), so a failure rolls the database back to the version it started at.

The SQL files themselves are also written to be re-runnable (``IF NOT EXISTS``,
catalog-guarded ``CREATE TYPE``), so applying them by hand through the Supabase SQL
editor or MCP is safe too.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from importlib import resources

import asyncpg

logger = logging.getLogger(__name__)


def advisory_key(label: bytes) -> int:
    """Stable signed 64-bit Postgres advisory-lock key derived from ``label``."""
    return int.from_bytes(hashlib.sha256(label).digest()[:8], "big", signed=True)


_ADVISORY_LOCK_KEY = advisory_key(b"plato.scientist.migrations")

_BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS plato;
CREATE TABLE IF NOT EXISTS plato.schema_migrations (
    version     TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class MigrationDriftError(RuntimeError):
    """An already-applied migration file no longer matches its recorded checksum."""


@dataclass(frozen=True)
class Migration:
    version: str
    sql: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def load_migrations() -> list[Migration]:
    """Return packaged migrations sorted by version (file name prefix)."""
    root = resources.files("plato.scientist.db") / "migrations"
    files = sorted(
        (entry for entry in root.iterdir() if entry.name.endswith(".sql")),
        key=lambda entry: entry.name,
    )
    return [Migration(f.name.removesuffix(".sql"), f.read_text("utf-8")) for f in files]


async def migrate(conn: asyncpg.Connection) -> list[str]:
    """Apply pending migrations. Returns the versions applied by this call."""
    applied_now: list[str] = []
    migrations = load_migrations()
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", _ADVISORY_LOCK_KEY)
        await conn.execute(_BOOTSTRAP_SQL)
        rows = await conn.fetch("SELECT version, sha256 FROM plato.schema_migrations")
        recorded = {r["version"]: r["sha256"] for r in rows}

        for migration in migrations:
            known = recorded.get(migration.version)
            if known is not None:
                if known != migration.sha256:
                    raise MigrationDriftError(
                        f"migration {migration.version} changed after it was applied "
                        f"(recorded {known[:12]}, file {migration.sha256[:12]}); "
                        "add a new migration instead of editing an applied one"
                    )
                continue
            # A savepoint per file: one bad migration rolls back alone and is reported.
            async with conn.transaction():
                await conn.execute(migration.sql)
                await conn.execute(
                    "INSERT INTO plato.schema_migrations(version, sha256) VALUES ($1, $2)",
                    migration.version,
                    migration.sha256,
                )
            applied_now.append(migration.version)
            logger.info("applied migration %s", migration.version)
    return applied_now


async def _main() -> None:  # pragma: no cover - operator entry point
    import os

    dsn = os.environ.get("PLATO_DATABASE_URL")
    if not dsn:
        raise SystemExit(
            "set PLATO_DATABASE_URL (Supabase session pooler, port 5432, sslmode=require)"
        )
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        applied = await migrate(conn)
        print(
            "applied:", ", ".join(applied) if applied else "nothing (schema up to date)"
        )
    finally:
        await conn.close()


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
