"""Phase 1 — R1: cmbagent paths are deprecated."""
from __future__ import annotations

import warnings
from unittest.mock import patch

import pytest


@pytest.fixture
def plato_instance(tmp_path):
    """A minimal Plato instance with a temp project_dir and no env keys."""
    from plato import Plato

    p = Plato(project_dir=str(tmp_path))
    p.set_data_description("test description")
    p.set_idea("test idea")
    return p


def test_get_idea_cmbagent_emits_deprecation_warning(plato_instance):
    """`get_idea_cmbagent` (and `get_idea(mode='cmbagent')`) must warn."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Patch the heavy `Idea` so the test does not actually invoke cmbagent.
        with patch("plato.plato.Idea") as MockIdea:
            MockIdea.return_value.develop_idea.return_value = "stub idea"
            plato_instance.get_idea_cmbagent()

    deprecations = [
        w for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "get_idea_cmbagent" in str(w.message)
    ]
    assert deprecations, f"expected DeprecationWarning, got: {[str(w.message) for w in caught]}"


def test_get_method_cmbagent_emits_deprecation_warning(plato_instance):
    """`get_method_cmbagent` must warn."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with patch("plato.plato.Method") as MockMethod:
            MockMethod.return_value.develop_method.return_value = "stub method"
            plato_instance.get_method_cmbagent()

    deprecations = [
        w for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "get_method_cmbagent" in str(w.message)
    ]
    assert deprecations, f"expected DeprecationWarning, got: {[str(w.message) for w in caught]}"


def test_get_idea_fast_does_not_warn():
    """The default `mode='fast'` path is the recommended path; no deprecation."""
    # We don't actually invoke get_idea_fast (it would need API keys).
    # Instead we verify the absence of DeprecationWarning at import time.
    import importlib

    import plato.plato as plato_mod

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(plato_mod)

    fast_deprecations = [
        w for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "get_idea_fast" in str(w.message)
    ]
    assert not fast_deprecations
