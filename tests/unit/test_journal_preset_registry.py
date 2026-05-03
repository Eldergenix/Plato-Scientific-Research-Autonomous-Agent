"""Tests for the JournalPreset registry (iter 16 / ADR 0003 phase 3).

The registry mirrors ``plato.paper_agents.latex_presets.journal_dict``
behind a string-keyed API so third-party domains can register additional
presets without monkey-patching the legacy enum-keyed dict.

What we pin:

1. Lazy-load fires on first lookup and seeds every built-in journal.
2. ``Journal.NONE`` (whose ``.value`` is ``None``) lands as the string
   ``"NONE"`` — the registry can never have a `None` key.
3. ``register_journal_preset`` rejects duplicates unless ``overwrite=True``
   and normalises names to upper-case.
4. The bundled `LatexPresets` instances are passed through unchanged.
"""
from __future__ import annotations

import pytest

from plato.journal_preset import (
    JOURNAL_PRESET_REGISTRY,
    get_journal_preset,
    list_journal_presets,
    register_journal_preset,
)


def test_lazy_load_seeds_all_journal_dict_entries() -> None:
    names = set(list_journal_presets())
    # These are the 12 journals shipped via journal_dict; the registry must
    # mirror every one of them.
    expected = {
        "NONE", "AAS", "APS", "ICML", "JHEP", "NeurIPS".upper(),
        "PASJ", "NATURE", "CELL", "SCIENCE", "PLOS_BIO", "ELIFE",
    }
    assert expected.issubset(names)


def test_none_journal_lands_as_string_key() -> None:
    """``Journal.NONE.value`` is ``None`` — must not poison the registry."""
    assert "NONE" in JOURNAL_PRESET_REGISTRY
    assert None not in JOURNAL_PRESET_REGISTRY  # type: ignore[operator]


def test_get_journal_preset_returns_underlying_latex_presets() -> None:
    from plato.paper_agents.journal import LatexPresets

    aas = get_journal_preset("AAS")
    assert isinstance(aas, LatexPresets)
    assert aas.article == "aastex631"  # pinned in latex_presets.py


def test_get_journal_preset_is_case_insensitive() -> None:
    upper = get_journal_preset("AAS")
    lower = get_journal_preset("aas")
    mixed = get_journal_preset("Aas")
    # Same instance reference across all three lookups.
    assert upper is lower is mixed


def test_get_unknown_preset_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_journal_preset("DEFINITELY_NOT_A_JOURNAL")


def test_register_journal_preset_collision_requires_overwrite() -> None:
    from plato.paper_agents.journal import LatexPresets

    stub = LatexPresets(article="article")  # smallest valid preset

    with pytest.raises(ValueError):
        register_journal_preset("AAS", stub)

    # overwrite=True replaces the entry.
    register_journal_preset("AAS", stub, overwrite=True)
    try:
        assert get_journal_preset("AAS").article == "article"
    finally:
        # Restore the real AAS preset so other tests aren't poisoned.
        from plato.paper_agents.latex_presets import latex_aas
        register_journal_preset("AAS", latex_aas, overwrite=True)


def test_register_journal_preset_normalises_name_to_upper() -> None:
    from plato.paper_agents.journal import LatexPresets

    stub = LatexPresets(article="article")
    register_journal_preset("My_Custom_Journal", stub, overwrite=True)
    try:
        assert get_journal_preset("MY_CUSTOM_JOURNAL") is stub
        # Lookup with mixed/lower case still works.
        assert get_journal_preset("my_custom_journal") is stub
    finally:
        JOURNAL_PRESET_REGISTRY.pop("MY_CUSTOM_JOURNAL", None)


def test_register_rejects_empty_name() -> None:
    from plato.paper_agents.journal import LatexPresets

    with pytest.raises(ValueError):
        register_journal_preset("", LatexPresets(article="article"))
