"""Concrete SourceAdapter implementations.

Importing this package side-effects ADAPTER_REGISTRY: each adapter module
below calls ``register_adapter(...)`` at import time. Without this re-export
``orchestrator.retrieve()`` falls through to "no usable adapters" and silently
returns an empty list — the entire literature stage becomes a no-op.

The order matches the typical retrieval profile (arXiv first because preprints
are usually freshest, then OpenAlex/Crossref/ADS for cross-publisher coverage,
then PubMed/Semantic Scholar for biomed/general). Order is cosmetic — the
registry keys uniquely on ``adapter.name``.
"""

from . import ads as _ads  # noqa: F401
from . import arxiv as _arxiv  # noqa: F401
from . import crossref as _crossref  # noqa: F401
from . import openalex as _openalex  # noqa: F401
from . import pubmed as _pubmed  # noqa: F401
from . import semantic_scholar as _semantic_scholar  # noqa: F401
