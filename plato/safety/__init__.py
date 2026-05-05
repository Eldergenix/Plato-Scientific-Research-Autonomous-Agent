"""
Plato safety package.

Phase 3 (R12): prompt-injection defenses for *external* text — abstracts,
search snippets, anything that did not originate inside Plato. The two
public helpers are:

* :func:`wrap_external` — quote external text inside an ``<external>``
  marker so downstream prompts can identify untrusted spans.
* :func:`detect_injection_signals` — surface red-flag patterns
  (override instructions, system pretexts, role-hijack phrases, base64
  blobs, hidden Unicode tag chars, etc.).
"""
from __future__ import annotations

from .sanitize import (
    PromptInjectionDetected,
    assert_safe,
    detect_injection_signals,
    is_suspicious,
    wrap_external,
)

__all__ = [
    "wrap_external",
    "detect_injection_signals",
    "is_suspicious",
    "assert_safe",
    "PromptInjectionDetected",
]
