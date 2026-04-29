"""
Phase 3 — R12: prompt-injection sanitizer for external text.

The functions here are *cheap, deterministic, and stdlib-only*. They are
not a substitute for sandboxing model output — they are a first-line
filter so calling code can decide whether to drop, flag, or quote a
suspicious span before feeding it into a prompt.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Wrapping
# ---------------------------------------------------------------------------

# Strip any ``<external ...>`` opening tag (with or without attributes) and
# any matching ``</external>`` closing tag. We do this *before* wrapping so an
# attacker cannot smuggle a fake ``</external>`` inside their abstract that
# would close our marker early.
_NESTED_EXTERNAL_RE = re.compile(r"</?\s*external\b[^>]*>", re.IGNORECASE)


def wrap_external(text: str, kind: str = "abstract") -> str:
    """Wrap ``text`` in an ``<external kind="...">...</external>`` marker.

    Any nested ``<external>`` tags inside ``text`` are stripped first, so
    untrusted input cannot prematurely close our outer marker or sneak in
    a forged inner wrapper.
    """
    cleaned = _NESTED_EXTERNAL_RE.sub("", text)
    return f'<external kind="{kind}">{cleaned}</external>'


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_OVERRIDE_RE = re.compile(
    r"(?i)ignore (the )?(previous|prior|above) (instructions?|prompt|system message)"
)
_SYSTEM_PRETEXT_RE = re.compile(r"(?im)^\s*(system|assistant)\s*:")
_ROLE_HIJACK_PHRASES = (
    "you are now a",
    "forget you are",
    "act as if you are",
)
_BASE64_RE = re.compile(r"[A-Za-z0-9+/=]{201,}")
# Unicode "tag" block U+E0000..U+E007F (used for invisible tag-character
# attacks) plus U+202E (right-to-left override).
_HIDDEN_UNICODE_RE = re.compile(r"[\U000E0000-\U000E007F‮]")


def detect_injection_signals(text: str) -> list[str]:
    """Return a list of red-flag signal names found in ``text``.

    Signals (in declaration order, deduped):

    * ``override_instruction``  — "ignore previous instructions" and friends.
    * ``system_pretext``        — a line starting with ``system:`` or ``assistant:``.
    * ``role_hijack``           — phrases like "you are now a calculator".
    * ``base64_blob``           — a base64-like run longer than 200 chars.
    * ``hidden_unicode``        — any U+E0000..U+E007F tag char or U+202E RLO.
    """
    signals: list[str] = []
    if _OVERRIDE_RE.search(text):
        signals.append("override_instruction")
    if _SYSTEM_PRETEXT_RE.search(text):
        signals.append("system_pretext")
    lowered = text.lower()
    if any(phrase in lowered for phrase in _ROLE_HIJACK_PHRASES):
        signals.append("role_hijack")
    if _BASE64_RE.search(text):
        signals.append("base64_blob")
    if _HIDDEN_UNICODE_RE.search(text):
        signals.append("hidden_unicode")
    return signals


def is_suspicious(text: str, threshold: int = 1) -> bool:
    """Return True if ``text`` contains at least ``threshold`` red flags."""
    return len(detect_injection_signals(text)) >= threshold


__all__ = ["wrap_external", "detect_injection_signals", "is_suspicious"]
