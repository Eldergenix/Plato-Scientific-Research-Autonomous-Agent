"""
Pluggable journal-preset registry (ADR 0003 Phase-3 stub).

A journal preset bundles the LaTeX template configuration for a single
journal: the document class, layout, abstract macro, bibliographystyle,
and any extra `.cls` / `.bst` / `.sty` files that need to be copied into
the project. The bundled `LatexPresets` Pydantic model already exists in
`plato.paper_agents.journal`; this module just exposes them through a
registry so third-party domains can add additional presets without
monkey-patching the existing `journal_dict`.

The registry mirrors the lazy-load pattern in `plato.executor` and
`plato.keyword_extractor`: built-in presets are registered the first time
the registry is queried, importing the existing `journal_dict` as the
source of truth. That way the legacy enum-keyed lookup keeps working AND
new entries become available at the new string-keyed API without
duplication.

Why this exists: `DomainProfile.journal_presets` is a list of preset
*names* (`["NATURE", "CELL", ...]`). Without a registry, those names had
to map to the hard-coded `Journal` enum — a third party adding a new
journal would need to edit the enum and `journal_dict` in the core
package. With this registry they just call
``register_journal_preset("MY_JOURNAL", LatexPresets(...))`` from a
side-module.
"""
from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ..paper_agents.journal import LatexPresets


__all__ = [
    "JOURNAL_PRESET_REGISTRY",
    "register_journal_preset",
    "get_journal_preset",
    "list_journal_presets",
]


JOURNAL_PRESET_REGISTRY: dict[str, "LatexPresets"] = {}


def register_journal_preset(
    name: str,
    presets: "LatexPresets",
    *,
    overwrite: bool = False,
) -> None:
    """Register a journal preset under a string key.

    Names are normalised to upper-case so callers can pass either the
    `Journal` enum value (`"AAS"`) or a free-form identifier
    (`"my_journal"` → stored as `"MY_JOURNAL"`).
    """
    key = (name or "").upper()
    if not key:
        raise ValueError("Journal preset name must be a non-empty string.")
    if not overwrite and key in JOURNAL_PRESET_REGISTRY:
        raise ValueError(
            f"Journal preset {key!r} is already registered; pass overwrite=True to replace."
        )
    JOURNAL_PRESET_REGISTRY[key] = presets


def get_journal_preset(name: str) -> "LatexPresets":
    """Look up a registered preset by name (lazy-loads the built-ins on first call)."""
    _ensure_builtins_registered()
    key = (name or "").upper()
    if key not in JOURNAL_PRESET_REGISTRY:
        raise KeyError(
            f"Unknown journal preset {name!r}. "
            f"Registered: {sorted(JOURNAL_PRESET_REGISTRY)}"
        )
    return JOURNAL_PRESET_REGISTRY[key]


def list_journal_presets() -> list[str]:
    """Return the sorted list of registered preset names."""
    _ensure_builtins_registered()
    return sorted(JOURNAL_PRESET_REGISTRY)


# --- Lazy registration of built-in presets ---------------------------------
# Defer the heavy import (`paper_agents.latex_presets` pulls the journal
# enum and every `LatexPresets` instance) until first use. That keeps
# `import plato.journal_preset` cheap, and also dodges a circular import
# if the registry is ever consumed from inside `paper_agents/`.

_builtins_loaded = False


def _ensure_builtins_registered() -> None:
    """Mirror `journal_dict` into the registry exactly once."""
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True

    try:
        from ..paper_agents.latex_presets import journal_dict
    except Exception:
        # If the legacy module fails to import we still want the registry
        # available — third parties can populate it manually.
        return

    for journal_key, preset in journal_dict.items():
        # journal_dict is keyed by the Journal enum; `.value` is the
        # canonical string identifier ("AAS", "APS", ...). NONE has a
        # value of None, which we surface as the string "NONE" so the
        # registry stays string-keyed.
        if hasattr(journal_key, "value") and journal_key.value is not None:
            name = str(journal_key.value)
        else:
            name = "NONE"
        register_journal_preset(name, preset, overwrite=True)
