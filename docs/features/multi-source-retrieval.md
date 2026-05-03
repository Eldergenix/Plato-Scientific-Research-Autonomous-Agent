# Multi-Source Retrieval

> R4. Six adapter retrieval orchestrator with rate-limit backoff,
> ETag caching, and per-host circuit breakers.

## Adapters shipped

| Adapter         | Module                                          | Notes |
|-----------------|-------------------------------------------------|-------|
| arxiv           | `plato/retrieval/sources/arxiv.py`              | Atom XML via stdlib (no `feedparser` dep) |
| openalex        | `plato/retrieval/sources/openalex.py`           | `/works` endpoint with mailto polite-pool header |
| ads             | `plato/retrieval/sources/ads.py`                | Astrophysics Data System; honours `ADS_API_KEY` |
| crossref        | `plato/retrieval/sources/crossref.py`           | DOI registry; also feeds the citation validator |
| pubmed          | `plato/retrieval/sources/pubmed.py`             | NCBI E-utilities (esearch → esummary → efetch) |
| semantic_scholar| `plato/retrieval/sources/semantic_scholar.py`   | S2 Graph API; honours `SEMANTIC_SCHOLAR_KEY` |

Each adapter implements the same `SourceAdapter` Protocol from
`plato/retrieval/__init__.py` and registers itself at module
import time via `register_adapter(...)`. Adding a new source is a
single new file plus the registration line.

## Domain-driven selection

The active `DomainProfile` (see ADR 0003) decides which adapters to
fan out to. `astro` ships with `[arxiv, openalex, ads,
semantic_scholar]`; `biology` ships with
`[pubmed, openalex, semantic_scholar]`. Override per-call with
`adapter_names=["arxiv", "openalex"]`.

## Orchestration

```python
from plato.retrieval.orchestrator import retrieve

sources = await retrieve(query="dark matter halos", limit=20, profile=astro)
```

Internals (`plato/retrieval/orchestrator.py`):

1. Pick adapters from `DomainProfile.retrieval_sources`.
2. Fan out via `asyncio.gather(...)` — every adapter searches in
   parallel. Adapter exceptions are caught and logged; one failing
   source can't crash the call.
3. Dedup by DOI / arxiv id / openalex id (prefer the richest hit).
4. Rerank via `plato/retrieval/reranker.py` — Cohere when
   `COHERE_API_KEY` is set, else `sentence-transformers` cross-
   encoder, else first-seen-wins (one-time warning).
5. Return top-K.

## Middleware

Every adapter sits behind `plato/retrieval/middleware.py`:

- **RateLimitBackoff** — exponential backoff with `Retry-After`
  header parsing on 429/503.
- **ETagCache** — filesystem-backed `~/.plato/cache/retrieval/`
  with conditional GET. Replays 304 responses instantly.
- **CircuitBreaker** — opens after N consecutive failures,
  auto-closes after a cooldown.

Disable the on-disk cache via `PLATO_DISABLE_RETRIEVAL_CACHE=1`
(useful for tests).

## See also

- ADR 0003 — Domain profile pluggability.
- `plato/retrieval/citation_graph.py` — 1-hop OpenAlex citation
  expansion (called from the dashboard's citation graph view).
- `docs/features/citation-validation.md` — the downstream consumer
  that validates every retrieved source's identifiers.
