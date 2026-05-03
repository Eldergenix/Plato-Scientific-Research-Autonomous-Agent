"""
The fallback `KeywordExtractor` used when no domain-specific extractor is
selected (or the selected one fails to import).

It returns the most frequent non-stopword tokens from the prompt — no LLM,
no network, no optional deps. The intent is to keep the keyword pipeline
running in environments where neither cmbagent nor an HTTP-backed extractor
is available, not to produce competitive keyword recommendations.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import register_keyword_extractor


__all__ = ["DefaultKeywordExtractor"]


# A small stoplist — just enough to avoid the obvious filler. We deliberately
# keep this tiny so `default` stays predictable; domain-aware extractors
# should be doing the heavy lifting.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "with",
        "is", "are", "was", "were", "be", "been", "being", "this", "that",
        "these", "those", "by", "from", "as", "at", "we", "our", "their",
        "its", "it", "i", "you", "he", "she", "they", "but", "if", "then",
        "than", "so", "such", "not", "no", "yes", "do", "does", "did",
        "have", "has", "had", "can", "could", "should", "would", "may",
        "might", "must", "will", "shall",
    }
)


def _tokenise(text: str) -> list[str]:
    # Lowercase + alphabetic sequences only, so numerals and punctuation drop
    # out. Keeps the implementation deterministic and dep-free.
    return [
        tok.lower()
        for tok in re.findall(r"[A-Za-z][A-Za-z\-]+", text)
        if tok.lower() not in _STOPWORDS and len(tok) > 2
    ]


class DefaultKeywordExtractor:
    """Frequency-based keyword extractor with no external dependencies."""

    name = "default"

    def extract(
        self,
        prompt: str,
        *,
        n_keywords: int = 8,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            return {}
        counts = Counter(_tokenise(prompt))
        top = counts.most_common(max(int(n_keywords or 0), 0))
        # Mirror the cmbagent return shape: keyword → (small) score dict.
        return {word: {"score": count} for word, count in top}


register_keyword_extractor(DefaultKeywordExtractor(), overwrite=True)
