import os
from pydantic import BaseModel
from dotenv import load_dotenv


# Whitelist of attribute names that may be read/written via [] subscripts.
# Without this, ``keys["OPENAI_API_KEY"]`` would silently set/return None on
# a typo'd attribute name and the user would never notice.
_ALLOWED_KEYS = frozenset({
    "ANTHROPIC", "GEMINI", "OPENAI", "PERPLEXITY", "SEMANTIC_SCHOLAR",
    "LANGFUSE_PUBLIC", "LANGFUSE_SECRET", "LANGFUSE_HOST",
})

# Backwards-compatible aliases. Pre-iter-2 callers indexed via the env-var
# spelling ("OPENAI_API_KEY", "GOOGLE_API_KEY", etc.). Translating those
# silently keeps the legacy contract working without re-introducing the
# typo-swallowing footgun: arbitrary attribute names still raise.
_KEY_ALIASES = {
    "OPENAI_API_KEY": "OPENAI",
    "GOOGLE_API_KEY": "GEMINI",
    "GEMINI_API_KEY": "GEMINI",
    "ANTHROPIC_API_KEY": "ANTHROPIC",
    "PERPLEXITY_API_KEY": "PERPLEXITY",
    "SEMANTIC_SCHOLAR_KEY": "SEMANTIC_SCHOLAR",
    "SEMANTIC_SCHOLAR_API_KEY": "SEMANTIC_SCHOLAR",
    "LANGFUSE_PUBLIC_KEY": "LANGFUSE_PUBLIC",
    "LANGFUSE_SECRET_KEY": "LANGFUSE_SECRET",
}


def _resolve_key(key: str) -> str:
    """Translate aliased env-style names back to canonical attribute names.

    Returns the canonical name for any name in either ``_ALLOWED_KEYS`` or
    ``_KEY_ALIASES``. Raises ``KeyError`` for everything else, preserving
    the typo-rejection guarantee for unknown names.
    """
    if key in _ALLOWED_KEYS:
        return key
    if key in _KEY_ALIASES:
        return _KEY_ALIASES[key]
    raise KeyError(
        f"Unknown key {key!r}. Valid keys: {sorted(_ALLOWED_KEYS)} "
        f"(legacy aliases also accepted: {sorted(_KEY_ALIASES)})"
    )


class KeyManager(BaseModel):
    ANTHROPIC: str | None = ""
    GEMINI: str | None = ""
    OPENAI: str | None = ""
    PERPLEXITY: str | None = ""
    SEMANTIC_SCHOLAR: str | None = ""
    LANGFUSE_PUBLIC: str | None = ""
    LANGFUSE_SECRET: str | None = ""
    LANGFUSE_HOST: str | None = ""

    def get_keys_from_env(self) -> None:

        load_dotenv()

        self.OPENAI           = os.getenv("OPENAI_API_KEY")
        self.GEMINI           = os.getenv("GOOGLE_API_KEY")
        self.ANTHROPIC        = os.getenv("ANTHROPIC_API_KEY") #not strictly needed
        self.PERPLEXITY       = os.getenv("PERPLEXITY_API_KEY") #only for citations
        self.SEMANTIC_SCHOLAR = os.getenv("SEMANTIC_SCHOLAR_KEY") #only for fast semantic scholar
        # Optional observability — only consumed if `langfuse` is installed.
        self.LANGFUSE_PUBLIC  = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.LANGFUSE_SECRET  = os.getenv("LANGFUSE_SECRET_KEY")
        self.LANGFUSE_HOST    = os.getenv("LANGFUSE_HOST")

    def clear(self) -> None:
        """Wipe every cached key value back to None.

        The dashboard's logout flow and key-rotation tooling want a way to
        guarantee no key value lingers in process memory after the user
        rotates a credential. Without this, a long-lived dashboard worker
        would carry the prior key indefinitely (no TTL, no cache eviction).
        Callers should follow up with ``get_keys_from_env`` if they want
        the env-side values reloaded.
        """
        for name in _ALLOWED_KEYS:
            setattr(self, name, None)

    def __getitem__(self, key: str) -> str | None:
        # Every KeyManager attribute is initialised to ``None`` when no
        # env var is set, so the honest return type is ``str | None``.
        # Previously declared ``-> str``, which lied to type-checkers
        # and let callers chain string ops on a value that could be
        # ``None`` at runtime. Unknown attribute names raise (typo
        # rejection); legacy env-style aliases like "OPENAI_API_KEY"
        # are transparently translated to canonical attribute names.
        return getattr(self, _resolve_key(key))

    def __setitem__(self, key: str, value: str | None) -> None:
        setattr(self, _resolve_key(key), value)
