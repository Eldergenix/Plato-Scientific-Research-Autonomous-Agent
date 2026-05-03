"""
MeSH-vocabulary keyword extractor for the `biology` `DomainProfile`.

The full MeSH (Medical Subject Headings) tree is large (~30k descriptors)
and ships from the National Library of Medicine; we don't bundle it here.
This extractor implements the registry contract by:

1. Tokenising the prompt with the same routine as `default`.
2. Filtering tokens against an optional MeSH dictionary file
   (``$PLATO_MESH_VOCAB`` env var pointing at a newline-delimited
   descriptor list — the MeSH ASCII export works directly).
3. Falling back to the frequency-based default behaviour if no vocab is
   configured, so a biology run never crashes for missing vocab.

Concrete sites that need real MeSH coverage should either point the env
var at ``mesh_descriptors.txt`` or register a richer extractor that hits
the NLM E-utilities API.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

from . import register_keyword_extractor
from .default import _tokenise


__all__ = ["MeshKeywordExtractor"]


def _load_vocab(path: str | Path) -> frozenset[str]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return frozenset()
    return frozenset(
        line.strip().lower()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    )


class MeshKeywordExtractor:
    """Keyword extractor that prefers tokens in the MeSH controlled vocabulary."""

    name = "mesh"

    def __init__(self) -> None:
        # Resolve the vocab file lazily so the env var can change between
        # tests without re-importing the module.
        self._vocab_path = os.environ.get("PLATO_MESH_VOCAB")
        self._vocab: frozenset[str] | None = None

    def _vocab_set(self) -> frozenset[str]:
        if self._vocab is None:
            self._vocab = _load_vocab(self._vocab_path) if self._vocab_path else frozenset()
        return self._vocab

    def extract(
        self,
        prompt: str,
        *,
        n_keywords: int = 8,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            return {}
        tokens = _tokenise(prompt)
        vocab = self._vocab_set()
        if vocab:
            tokens = [t for t in tokens if t in vocab]
        counts = Counter(tokens)
        top = counts.most_common(max(int(n_keywords or 0), 0))
        return {word: {"score": count, "vocab": "mesh"} for word, count in top}


register_keyword_extractor(MeshKeywordExtractor(), overwrite=True)
