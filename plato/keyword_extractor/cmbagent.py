"""
The cmbagent-backed `KeywordExtractor` — the default for the `astro`
`DomainProfile`.

Wraps `cmbagent.get_keywords` so the registry indirection doesn't change
the returned shape. cmbagent itself is an optional dep in some
environments (CI without LLM keys, for instance), so the import is
deferred to `extract()` and a clear error is raised at call time if it's
missing.
"""
from __future__ import annotations

from typing import Any

from . import register_keyword_extractor


__all__ = ["CmbagentKeywordExtractor"]


class CmbagentKeywordExtractor:
    """Extractor that delegates to `cmbagent.get_keywords`."""

    name = "cmbagent"

    def extract(
        self,
        prompt: str,
        *,
        n_keywords: int = 8,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Lazy import: cmbagent pulls a heavy transitive graph and may not
        # be importable in every environment. We only fail when an astro
        # run actually asks for keywords, not at registry-load time.
        try:
            import cmbagent
        except Exception as exc:  # pragma: no cover — exercised in error path tests
            raise RuntimeError(
                "cmbagent is not importable in this environment; "
                "install plato with the cmbagent extra or pick a different "
                "DomainProfile.keyword_extractor."
            ) from exc

        # ``cmbagent.get_keywords`` returns a dict keyed by keyword; we pass
        # extra kwargs through (``kw_type``, ``api_keys``, ...) so callers
        # keep parity with the legacy direct call.
        return cmbagent.get_keywords(prompt, n_keywords=n_keywords, **kwargs)


register_keyword_extractor(CmbagentKeywordExtractor(), overwrite=True)
