"""
Pluggable keyword-extractor registry (ADR 0003 Phase-3 stub).

A `KeywordExtractor` takes a textual prompt (typically a research idea or
abstract) and returns a dictionary of suggested paper keywords. The dict
shape mirrors what `cmbagent.get_keywords` already returns — keys are the
keyword strings, values are extractor-specific metadata (often a score) —
so existing call sites can swap implementations transparently.

The registry follows the same lazy-load pattern as `plato.executor`:
built-in implementations live in side-modules (`cmbagent.py`, `mesh.py`,
`openalex_concepts.py`, `default.py`) and register themselves the first
time `get_keyword_extractor` or `list_keyword_extractors` is called. This
keeps `import plato.keyword_extractor` cheap when no extractor is needed.

Why this exists: `DomainProfile.keyword_extractor` is a string identifier
(`"cmbagent"`, `"mesh"`, ...) that previously didn't resolve to anything
— picking a non-astro domain silently fell back to the hard-coded cmbagent
path in `paper_node.py`. With this registry in place the domain profile
controls which extractor runs, and third-party domains can register their
own without touching Plato.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


__all__ = [
    "KeywordExtractor",
    "KEYWORD_EXTRACTOR_REGISTRY",
    "register_keyword_extractor",
    "get_keyword_extractor",
    "list_keyword_extractors",
]


@runtime_checkable
class KeywordExtractor(Protocol):
    """Protocol every keyword-extractor backend must implement."""

    name: str
    """Stable identifier matching `DomainProfile.keyword_extractor` entries."""

    def extract(
        self,
        prompt: str,
        *,
        n_keywords: int = 8,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return a dict whose keys are suggested keywords.

        Implementations are free to put extractor-specific metadata in the
        values (e.g. a score, a controlled-vocabulary URI, ...). Callers
        that just want the keyword strings should use ``.keys()``.
        """
        ...


KEYWORD_EXTRACTOR_REGISTRY: dict[str, KeywordExtractor] = {}


def register_keyword_extractor(
    extractor: KeywordExtractor,
    *,
    overwrite: bool = False,
) -> None:
    """Register a `KeywordExtractor`. Raises if the name collides unless `overwrite=True`."""
    if not overwrite and extractor.name in KEYWORD_EXTRACTOR_REGISTRY:
        raise ValueError(
            f"KeywordExtractor {extractor.name!r} is already registered; "
            "pass overwrite=True to replace."
        )
    KEYWORD_EXTRACTOR_REGISTRY[extractor.name] = extractor


def get_keyword_extractor(name: str) -> KeywordExtractor:
    """Look up a registered extractor by name (lazy-loads built-ins on first call)."""
    _ensure_builtins_registered()
    if name not in KEYWORD_EXTRACTOR_REGISTRY:
        raise KeyError(
            f"Unknown keyword extractor {name!r}. "
            f"Registered: {sorted(KEYWORD_EXTRACTOR_REGISTRY)}"
        )
    return KEYWORD_EXTRACTOR_REGISTRY[name]


def list_keyword_extractors() -> list[str]:
    """Return the sorted list of registered extractor names."""
    _ensure_builtins_registered()
    return sorted(KEYWORD_EXTRACTOR_REGISTRY)


# --- Lazy registration of built-in extractors ------------------------------
# Mirrors the deferral pattern in `plato.executor`: built-in modules each
# call `register_keyword_extractor(...)` on import. We only fire those
# imports on first `get_*` / `list_*` call so importing this module is
# cheap, and an unavailable optional dep (e.g. cmbagent missing in CI)
# only breaks the one extractor that depends on it.

_BUILTIN_EXTRACTORS: tuple[str, ...] = (
    "default",
    "cmbagent",
    "mesh",
    "openalex_concepts",
)
_builtins_loaded = False


def _ensure_builtins_registered() -> None:
    """Import every built-in extractor module exactly once."""
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    import importlib

    for name in _BUILTIN_EXTRACTORS:
        try:
            importlib.import_module(f".{name}", __name__)
        except Exception:
            # Optional-dep failures (cmbagent, requests, ...) shouldn't
            # break the other extractors. Each module handles its own
            # missing-dep behaviour at extract() time.
            pass
