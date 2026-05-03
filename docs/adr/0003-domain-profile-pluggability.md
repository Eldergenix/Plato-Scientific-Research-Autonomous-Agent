# ADR 0003 — Domain pluggability via `DomainProfile` registry

- **Status**: Accepted
- **Date**: 2026-04-30
- **Deciders**: Plato maintainers
- **Phase**: 1 (Stabilize) → exercised in Phase 5

## Context

The architectural review (§5.9) flagged that several pieces of Plato
were quietly astro-coded:

- `cmbagent.get_keywords()` was the only keyword extractor.
- The `Journal` enum shipped only AAS / APS / JHEP / PASJ presets.
- The single retrieval source was Semantic Scholar; no hook for
  PubMed (biology), arXiv-only modes, ADS (astro), etc.
- `get_results()` always dispatched to the cmbagent executor.

A non-astro user couldn't pick a different stack without forking the
codebase. The reviewer wanted a way to keep astro as the default but
expose every astro-coded primitive as a swap point.

## Decision

Introduce a `DomainProfile` Pydantic model in `plato/domain/__init__.py`
that bundles every domain-shaped knob into a single, registry-resolved
object:

```python
class DomainProfile(BaseModel):
    name: str                     # "astro" | "biology" | ...
    retrieval_sources: list[str]  # adapter names from ADAPTER_REGISTRY
    keyword_extractor: str        # name in KEYWORD_EXTRACTOR_REGISTRY
    journal_presets: list[str]    # subset of JOURNAL_PRESET_REGISTRY
    executor: str                 # name in EXECUTOR_REGISTRY
    novelty_corpus: str           # adapter-side corpus selector
```

`Plato(domain="astro")` resolves the profile from a process-local
`DOMAIN_REGISTRY`. Astro is registered out-of-the-box; non-astro
profiles register themselves at import time:

```python
register_domain(DomainProfile(name="biology", ...))
```

Each domain-shaped capability is a Protocol-typed registry of its own
(`SourceAdapter`, `Executor`, …) so a third-party plug-in can ship a
package, import its module, and have its components light up without
any core change.

## Consequences

**Positive.**

- Astro stays the default — no behaviour change for existing users.
- Adding a new domain becomes a side-module change, not a fork.
- Each registry is a focused contract that can be tested independently.

**Negative.**

- Side-effect imports become load-bearing: if a plug-in module isn't
  imported, its `register_domain(...)` call never runs and the profile
  is silently absent from the dashboard. We mitigate by registering
  the built-in profiles inside `plato/domain/__init__.py`.

**Neutral.**

- `Plato.__init__` now accepts `domain: str | DomainProfile = "astro"`;
  callers that don't pass it keep working unchanged.

## Status of the registries

| Registry              | Defined in                        | Built-in entries                                                    |
| --------------------- | --------------------------------- | ------------------------------------------------------------------- |
| `DomainProfile`       | `plato/domain/__init__.py`        | `astro`, `biology`                                                  |
| `SourceAdapter`       | `plato/retrieval/__init__.py`     | `arxiv`, `openalex`, `ads`, `crossref`, `pubmed`, `semantic_scholar`|
| `Executor`            | `plato/executor/__init__.py`      | `cmbagent`, `local_jupyter`*, `modal`*, `e2b`*                      |
| `KeywordExtractor`    | (planned — Phase 6)               | n/a                                                                 |
| `JournalPreset`       | `plato/paper_agents/journal.py`   | `NONE`, `AAS`, `APS`, `JHEP`, `PASJ`, `ICML`, `NeurIPS`             |

`*` = stub implementation; raises `NotImplementedError` on `run()`.

## See also

- ADR 0002 — Postgres checkpointer (sibling Phase-5 hardening).
- ADR 0005 — Sandboxed Executor protocol (this ADR's executor field).
- §5.9 of the architectural review for the full pluggability rationale.
