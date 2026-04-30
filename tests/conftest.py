"""Top-level pytest configuration shared by every test directory.

This file ships exactly one piece of cross-cutting test plumbing: a
session-wide snapshot/restore of the global registries that adapter and
tool modules populate at import time. Without it, tests that mutate
those registries (clear-and-repopulate, register a fake, swap a real
implementation) leak state into sibling tests and produce flaky failures
that depend on import order.

The fixture is **autouse** at function scope so every individual test
gets a clean slate without having to opt in.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_global_registries():
    """Snapshot the adapter + tool registries; restore them after the test.

    Tests that legitimately mutate the registries (e.g. ``register_adapter``
    of a fake) need no setup — the snapshot at function entry captures the
    pristine state, and the restore at exit puts it back.
    """
    # Late imports so this fixture loads even if a module has a side-effect
    # registration we wouldn't want to trigger at conftest-collection time.
    from plato.retrieval import ADAPTER_REGISTRY
    from plato.tools.registry import _REGISTRY as TOOL_REGISTRY

    adapter_snapshot = dict(ADAPTER_REGISTRY)
    tool_snapshot = dict(TOOL_REGISTRY)
    try:
        yield
    finally:
        ADAPTER_REGISTRY.clear()
        ADAPTER_REGISTRY.update(adapter_snapshot)
        TOOL_REGISTRY.clear()
        TOOL_REGISTRY.update(tool_snapshot)
