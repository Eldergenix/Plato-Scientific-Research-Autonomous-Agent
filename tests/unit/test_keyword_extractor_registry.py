"""Tests for the KeywordExtractor Protocol registry (iter 16 / ADR 0003 phase 3).

The registry must satisfy three properties:

1. The four built-in extractors auto-register on first lookup.
2. ``register_keyword_extractor`` rejects duplicates unless ``overwrite=True``.
3. The default extractor returns a `dict[str, dict]` payload that callers
   can ``.keys()`` and join, exactly like ``cmbagent.get_keywords`` does.

We deliberately do not exercise the network paths (cmbagent / OpenAlex) —
those depend on optional deps and live network. A smoke check that the
modules *register* their backends is enough.
"""
from __future__ import annotations

import pytest

from plato.keyword_extractor import (
    KEYWORD_EXTRACTOR_REGISTRY,
    KeywordExtractor,
    get_keyword_extractor,
    list_keyword_extractors,
    register_keyword_extractor,
)


def test_lazy_load_populates_default_set() -> None:
    """First call to ``list_keyword_extractors`` must seed the four built-ins."""
    names = list_keyword_extractors()
    assert {"default", "cmbagent", "mesh", "openalex_concepts"}.issubset(set(names))


def test_default_extractor_returns_dict_keyed_by_keyword() -> None:
    extractor = get_keyword_extractor("default")
    out = extractor.extract(
        "Cosmological perturbation theory in the cosmic microwave background",
        n_keywords=4,
    )
    assert isinstance(out, dict)
    assert 0 < len(out) <= 4
    # Existing call sites do ``", ".join(keywords.keys())`` — must work.
    joined = ", ".join(out.keys())
    assert isinstance(joined, str) and "," in joined or len(out) == 1


def test_default_extractor_handles_empty_prompt() -> None:
    extractor = get_keyword_extractor("default")
    assert extractor.extract("", n_keywords=8) == {}
    assert extractor.extract("   ", n_keywords=8) == {}


def test_default_extractor_filters_stopwords() -> None:
    extractor = get_keyword_extractor("default")
    out = extractor.extract("the the the and and quasar quasar quasar", n_keywords=3)
    # ``the`` / ``and`` are stopwords; ``quasar`` is the only signal.
    assert "quasar" in out.keys()
    assert "the" not in out.keys()


def test_get_unknown_extractor_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_keyword_extractor("definitely-not-registered")


def test_register_keyword_extractor_collision_requires_overwrite() -> None:
    class _Stub:
        name = "default"  # collides with the built-in

        def extract(self, prompt, *, n_keywords=8, **kwargs):
            return {}

    with pytest.raises(ValueError):
        register_keyword_extractor(_Stub())  # type: ignore[arg-type]

    # ``overwrite=True`` must succeed and replace the entry.
    register_keyword_extractor(_Stub(), overwrite=True)  # type: ignore[arg-type]
    try:
        assert KEYWORD_EXTRACTOR_REGISTRY["default"].extract("anything") == {}
    finally:
        # Restore the real default extractor for downstream tests.
        from plato.keyword_extractor.default import DefaultKeywordExtractor
        register_keyword_extractor(DefaultKeywordExtractor(), overwrite=True)


def test_runtime_checkable_protocol_recognises_default_instance() -> None:
    extractor = get_keyword_extractor("default")
    # ``runtime_checkable`` Protocol membership: the duck-typed default
    # extractor must satisfy ``isinstance(_, KeywordExtractor)``.
    assert isinstance(extractor, KeywordExtractor)


def test_mesh_extractor_falls_back_to_default_when_no_vocab() -> None:
    """Without ``$PLATO_MESH_VOCAB`` configured, the mesh extractor must still return tokens."""
    extractor = get_keyword_extractor("mesh")
    out = extractor.extract("photosynthesis photosynthesis enzyme catalysis", n_keywords=3)
    assert isinstance(out, dict)
    assert "photosynthesis" in out  # frequency-based fallback should pick it up
