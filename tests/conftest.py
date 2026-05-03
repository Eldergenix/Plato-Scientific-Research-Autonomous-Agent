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

import sys

import pytest


# Backend modules that some tests deliberately re-import under a patched
# ``builtins.__import__`` to verify the lazy-load gate (see
# ``tests/unit/test_modal_executor.py::test_module_imports_when_sdk_missing``
# and the e2b twin). The re-import populates ``sys.modules`` with a
# fresh module instance — and crucially, that fresh instance defines a
# *new* ``ModalExecutor`` / ``E2BExecutor`` class, which the executor
# registry then caches via ``register_executor(..., overwrite=True)``.
# Without snapshot/restore, every sibling test that touches
# ``get_executor("modal")`` ends up with a foreign class identity and
# loses access to attributes (``_lazy_init``, ``_check_credentials``)
# that the original instance carried. We restore both the module entry
# and the executor registry to keep the test universe consistent.
_LAZY_RE_IMPORT_MODULES: tuple[str, ...] = (
    "plato.executor.modal_backend",
    "plato.executor.e2b_backend",
)


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

    # Iter-16 additions: KeywordExtractor + JournalPreset registries follow
    # the same import-time side-effect pattern as the adapter / tool ones,
    # so they need the same snapshot-restore plumbing or any test that
    # exercises ``register_*`` will leak fakes into siblings.
    from plato.keyword_extractor import KEYWORD_EXTRACTOR_REGISTRY
    from plato.journal_preset import JOURNAL_PRESET_REGISTRY

    # Iter-18: executor registry + the backend ``sys.modules`` entries
    # that ``test_module_imports_when_sdk_missing`` deliberately re-imports.
    # Force the lazy built-in registration *before* we snapshot so the
    # baseline always contains all four backends — otherwise we'd
    # restore to a half-populated registry whenever the first test in a
    # session hits this fixture before any test calls ``get_executor``.
    from plato.executor import EXECUTOR_REGISTRY, list_executors
    list_executors()

    adapter_snapshot = dict(ADAPTER_REGISTRY)
    tool_snapshot = dict(TOOL_REGISTRY)
    keyword_extractor_snapshot = dict(KEYWORD_EXTRACTOR_REGISTRY)
    journal_preset_snapshot = dict(JOURNAL_PRESET_REGISTRY)
    executor_snapshot = dict(EXECUTOR_REGISTRY)
    backend_module_snapshot = {
        name: sys.modules[name] for name in _LAZY_RE_IMPORT_MODULES if name in sys.modules
    }
    try:
        yield
    finally:
        ADAPTER_REGISTRY.clear()
        ADAPTER_REGISTRY.update(adapter_snapshot)
        TOOL_REGISTRY.clear()
        TOOL_REGISTRY.update(tool_snapshot)
        KEYWORD_EXTRACTOR_REGISTRY.clear()
        KEYWORD_EXTRACTOR_REGISTRY.update(keyword_extractor_snapshot)
        JOURNAL_PRESET_REGISTRY.clear()
        JOURNAL_PRESET_REGISTRY.update(journal_preset_snapshot)
        EXECUTOR_REGISTRY.clear()
        EXECUTOR_REGISTRY.update(executor_snapshot)
        for name in _LAZY_RE_IMPORT_MODULES:
            cached = backend_module_snapshot.get(name)
            if cached is not None:
                sys.modules[name] = cached
            else:
                sys.modules.pop(name, None)
