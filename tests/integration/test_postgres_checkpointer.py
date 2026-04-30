"""Phase 5 — R2 verification: Postgres checkpointer integration.

Mirrors :mod:`tests.integration.test_checkpoint_resume` but exercises the
``postgres`` branch of :func:`plato.state.make_checkpointer`. The factory
already exists; this module is the missing acceptance test.

The whole module skips cleanly when Postgres is unavailable, so the
default ``pytest`` run on a developer laptop and the lightweight
``test-fast`` CI job stay green:

- ``langgraph-checkpoint-postgres`` is treated as an optional extra and
  skipped via :func:`pytest.importorskip` when missing.
- ``PLATO_POSTGRES_DSN`` must be set; otherwise we have no server to talk
  to and skip with an explicit message.

To run locally: ``docker run -p 5432:5432 -e POSTGRES_PASSWORD=plato postgres:16; export PLATO_POSTGRES_DSN=postgresql://postgres:plato@localhost:5432/postgres; pytest tests/integration/test_postgres_checkpointer.py``.
"""
from __future__ import annotations

import os
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from plato.state import make_checkpointer

# Skip the entire module unless both the extra package and a DSN are present.
pytest.importorskip(
    "langgraph.checkpoint.postgres",
    reason="langgraph-checkpoint-postgres is not installed; "
    "install it with `pip install langgraph-checkpoint-postgres` to run this suite.",
)

DSN = os.getenv("PLATO_POSTGRES_DSN")
if not DSN:
    pytest.skip(
        "PLATO_POSTGRES_DSN is not set; export it to run the postgres "
        "checkpointer integration suite (see module docstring).",
        allow_module_level=True,
    )


class _CounterState(TypedDict, total=False):
    counter: int


def _step1(state: _CounterState) -> _CounterState:
    return {"counter": state.get("counter", 0) + 1}


def _step2(state: _CounterState) -> _CounterState:
    return {"counter": state.get("counter", 0) + 10}


def _build(checkpointer, *, halt_after: int = 1):
    """Compile the same 2-node counter graph used by the sqlite resume test."""
    g = StateGraph(_CounterState)
    g.add_node("step1", _step1)
    g.add_node("step2", _step2)
    g.add_edge(START, "step1")

    def router(_state: _CounterState):
        return END if halt_after == 1 else "step2"

    g.add_conditional_edges("step1", router)
    g.add_edge("step2", END)
    return g.compile(checkpointer=checkpointer)


def _drop_checkpoint_tables(dsn: str) -> None:
    """Remove the LangGraph checkpoint tables so reruns start clean.

    PostgresSaver creates ``checkpoints``, ``checkpoint_blobs``,
    ``checkpoint_writes``, and ``checkpoint_migrations``. Dropping them
    keeps repeated test runs deterministic without nuking unrelated
    tables in the database.
    """
    psycopg = pytest.importorskip("psycopg")
    tables = (
        "checkpoint_writes",
        "checkpoint_blobs",
        "checkpoints",
        "checkpoint_migrations",
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


@pytest.fixture(scope="module")
def postgres_dsn() -> str:
    """The validated DSN for the test session.

    Wipes checkpoint tables before AND after the module runs so a partial
    run from a previous invocation doesn't poison this one and we leave
    the database clean for the next caller.
    """
    _drop_checkpoint_tables(DSN)
    yield DSN
    _drop_checkpoint_tables(DSN)


@pytest.fixture
def fresh_postgres(postgres_dsn: str) -> str:
    """Per-test cleanup so tests don't observe each other's checkpoints."""
    _drop_checkpoint_tables(postgres_dsn)
    return postgres_dsn


def test_make_checkpointer_returns_working_postgres_saver(fresh_postgres: str):
    """Smoke test: the factory returns a usable PostgresSaver context.

    ``PostgresSaver.from_conn_string`` returns a context manager that
    yields the saver. Entering it should succeed and ``setup()`` must run
    without error against a real database.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    saver_ctx = make_checkpointer("postgres", dsn=fresh_postgres)

    # The factory hands back the context manager from from_conn_string.
    with saver_ctx as saver:
        assert isinstance(saver, PostgresSaver), (
            f"Expected PostgresSaver, got {type(saver).__name__}"
        )
        # setup() is idempotent and creates the checkpoint tables.
        saver.setup()


def test_postgres_checkpoint_persists_across_invocations(fresh_postgres: str):
    """Same shape as the sqlite resume test, against postgres.

    Invoke once under ``thread_id="A"``, drop the graph and the saver,
    rebuild both pointing at the same DSN, and confirm the state for
    ``"A"`` is still there.
    """
    config = {"configurable": {"thread_id": "A"}}

    with make_checkpointer("postgres", dsn=fresh_postgres) as cp_first:
        cp_first.setup()
        graph_first = _build(cp_first, halt_after=1)
        out = graph_first.invoke({"counter": 0}, config=config)
        assert out == {"counter": 1}
        del graph_first

    # New process simulation: brand-new context manager, same DSN.
    with make_checkpointer("postgres", dsn=fresh_postgres) as cp_resumed:
        graph_resumed = _build(cp_resumed, halt_after=1)
        snapshot = graph_resumed.get_state(config=config)

    assert snapshot.values == {"counter": 1}, (
        "Expected the step1 increment from invocation #1 to be persisted in "
        f"postgres; got {snapshot.values!r}."
    )
    assert snapshot.next == ()


def test_two_threads_isolated(fresh_postgres: str):
    """Threads ``A`` and ``B`` share the database but stay independent."""
    with make_checkpointer("postgres", dsn=fresh_postgres) as cp:
        cp.setup()
        graph = _build(cp, halt_after=1)

        out_a = graph.invoke(
            {"counter": 0}, config={"configurable": {"thread_id": "A"}}
        )
        out_b = graph.invoke(
            {"counter": 0}, config={"configurable": {"thread_id": "B"}}
        )
        assert out_a == {"counter": 1}
        assert out_b == {"counter": 1}

    # Reconnect, advance only thread A, confirm thread B is untouched.
    with make_checkpointer("postgres", dsn=fresh_postgres) as cp_resumed:
        graph_resumed = _build(cp_resumed, halt_after=1)

        snap_a = graph_resumed.get_state(
            config={"configurable": {"thread_id": "A"}}
        )
        snap_b = graph_resumed.get_state(
            config={"configurable": {"thread_id": "B"}}
        )
        assert snap_a.values == {"counter": 1}
        assert snap_b.values == {"counter": 1}

        out_a2 = graph_resumed.invoke(
            {"counter": 5}, config={"configurable": {"thread_id": "A"}}
        )
        assert out_a2 == {"counter": 6}

        snap_b_after = graph_resumed.get_state(
            config={"configurable": {"thread_id": "B"}}
        )
        assert snap_b_after.values == {"counter": 1}, (
            "Mutating thread A must not affect thread B; "
            f"got B={snap_b_after.values!r}."
        )


def test_cleanup_drops_checkpoint_tables(postgres_dsn: str):
    """Sanity-check the teardown helper: after dropping, tables are gone.

    This guards the deterministic-rerun guarantee. If ``_drop_checkpoint_tables``
    silently fails to drop one of the tables, a previous test's data could
    leak into the next run and produce flaky results.
    """
    psycopg = pytest.importorskip("psycopg")

    # Make sure the tables exist first.
    with make_checkpointer("postgres", dsn=postgres_dsn) as cp:
        cp.setup()

    _drop_checkpoint_tables(postgres_dsn)

    expected = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
    with psycopg.connect(postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(%s)",
                [list(expected)],
            )
            remaining = {row[0] for row in cur.fetchall()}

    assert remaining == set(), (
        f"Expected checkpoint tables to be dropped; still found: {remaining!r}"
    )
