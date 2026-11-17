"""Fixtures for the dual-graph scientist tests.

Database tests run against a real PostgreSQL server (15+). Point
``PLATO_TEST_POSTGRES_DSN`` at a role that may create databases, e.g.::

    export PLATO_TEST_POSTGRES_DSN=postgresql://postgres@localhost:5432/postgres

Each test gets a brand-new database that is dropped afterwards, so tests are
isolated and can run the real migrations from scratch.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest

asyncpg = pytest.importorskip("asyncpg")

# PLATO_POSTGRES_DSN is the variable the other Postgres suites already use.
ADMIN_DSN = os.environ.get("PLATO_TEST_POSTGRES_DSN") or os.environ.get("PLATO_POSTGRES_DSN", "")


def _with_db(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


@pytest.fixture
async def pg_dsn():
    if not ADMIN_DSN:
        pytest.skip("PLATO_TEST_POSTGRES_DSN is not set")
    name = f"plato_t_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    try:
        yield _with_db(ADMIN_DSN, name)
    finally:
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.fixture
async def store(pg_dsn):
    from plato.scientist.db.store import DualGraphStore

    s = await DualGraphStore.connect(pg_dsn, max_size=20)
    try:
        yield s
    finally:
        await s.close()


@pytest.fixture
async def campaign(store):
    program = await store.ensure_program("test-program", "Test", "ml_systems")
    cid = await store.create_campaign(program, "Does feature scaling change k-NN accuracy?",
                                      token_budget_max=1_000_000)
    return program, cid
