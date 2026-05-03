"""
OpenAlex Concepts keyword extractor.

OpenAlex exposes a ``GET /concepts`` endpoint that ranks concepts by
relevance to a search string. We use it as a domain-agnostic alternative
to the cmbagent / MeSH paths — useful for ML, chemistry, social-science
profiles where neither astro nor biology vocabularies are appropriate.

The HTTP call is deliberately blocking and short-timeout: this method is
called once per paper from the keywords node, not in a hot loop. We
also avoid pulling in `httpx` as a hard dep — `urllib` is sufficient.

Reference: https://docs.openalex.org/api-entities/concepts
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from . import register_keyword_extractor


__all__ = ["OpenAlexConceptsKeywordExtractor"]


_OPENALEX_URL = "https://api.openalex.org/concepts"
_TIMEOUT_SECONDS = 8.0


class OpenAlexConceptsKeywordExtractor:
    """Keyword extractor that queries OpenAlex Concepts for ranked matches."""

    name = "openalex_concepts"

    def extract(
        self,
        prompt: str,
        *,
        n_keywords: int = 8,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            return {}

        # OpenAlex truncates very long ?search payloads — 240 chars is
        # the soft limit they document. We trim conservatively and let
        # the relevance scoring surface the strongest matches.
        query = prompt.strip()[:240]
        params = urllib.parse.urlencode(
            {
                "search": query,
                "per_page": max(int(n_keywords or 0), 1),
            }
        )
        url = f"{_OPENALEX_URL}?{params}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "plato-keyword-extractor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        except Exception:
            # Network errors must not abort a paper run. Return an empty
            # dict so the caller can fall back to the default extractor or
            # an empty keyword list.
            return {}

        results = payload.get("results") or []
        out: dict[str, Any] = {}
        for entry in results[: max(int(n_keywords or 0), 0)]:
            label = (entry.get("display_name") or "").strip()
            if not label:
                continue
            out[label] = {
                "score": float(entry.get("relevance_score") or 0.0),
                "openalex_id": entry.get("id"),
                "level": entry.get("level"),
            }
        return out


register_keyword_extractor(OpenAlexConceptsKeywordExtractor(), overwrite=True)
