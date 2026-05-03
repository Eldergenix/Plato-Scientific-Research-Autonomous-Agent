# Domain Pluggability

> §5.9 + ADR 0003. `DomainProfile` registry exposes retrieval
> sources, keyword extractor, journal presets, executor, and
> novelty corpus as swap points. Astro is the default; biology
> ships out-of-the-box.

## What's a DomainProfile?

```python
class DomainProfile(BaseModel):
    name: str                    # "astro" | "biology" | ...
    retrieval_sources: list[str] # SourceAdapter names from ADAPTER_REGISTRY
    keyword_extractor: str       # KeywordExtractor name from KEYWORD_EXTRACTOR_REGISTRY
    journal_presets: list[str]   # Journal enum values
    executor: str                # Executor name from EXECUTOR_REGISTRY
    novelty_corpus: str          # adapter-side corpus selector
```

`Plato(domain="biology")` looks up the profile via
`get_domain("biology")` and instantiates the matching adapters /
executor at construction time. No core code changes for a new
domain — just register a profile and ship it.

## Built-in profiles

### Astro (default)

```python
DomainProfile(
    name="astro",
    retrieval_sources=["arxiv", "openalex", "ads", "semantic_scholar"],
    keyword_extractor="cmbagent",
    journal_presets=["AAS", "APS", "JHEP", "PASJ", "ICML", "NeurIPS", "NONE"],
    executor="cmbagent",
    novelty_corpus="arxiv:astro-ph",
)
```

### Biology

```python
DomainProfile(
    name="biology",
    retrieval_sources=["pubmed", "openalex", "semantic_scholar"],
    keyword_extractor="mesh",
    journal_presets=["NATURE", "CELL", "SCIENCE", "PLOS_BIO", "ELIFE"],
    executor="local_jupyter",
    novelty_corpus="pubmed",
)
```

## Adding a domain

```python
from plato.domain import DomainProfile, register_domain

register_domain(DomainProfile(
    name="chemistry",
    retrieval_sources=["openalex", "semantic_scholar"],
    keyword_extractor="cmbagent",
    journal_presets=["NONE"],
    executor="local_jupyter",
    novelty_corpus="openalex:chemistry",
))
```

Side-effect imports are how non-astro domains opt in — call
`register_domain(...)` from a side module loaded via PYTHONPATH or
a setup-time hook.

## Dashboard view

`/settings/domains` lists every registered profile, lets the user
pick a default per-tenant via `/api/v1/user/preferences`, and
shows the adapter / executor list for the active selection. The
DomainSelector dropdown drives the preview without saving until
"Set as default" is clicked.

## Registry primitives

The four supporting registries each follow the same Protocol +
auto-registration pattern:

| Registry        | Module                              | Built-ins                         |
|-----------------|-------------------------------------|-----------------------------------|
| DomainProfile   | `plato/domain/__init__.py`          | astro, biology                    |
| SourceAdapter   | `plato/retrieval/__init__.py`       | arxiv, openalex, ads, crossref, pubmed, semantic_scholar |
| Executor        | `plato/executor/__init__.py`        | cmbagent, local_jupyter (stub), modal (stub), e2b (stub) |
| KeywordExtractor| `plato/keyword_extractor/`          | Shipped in iter 16; see `plato/keyword_extractor/` for the registry. |

## See also

- ADR 0003 — Domain profile pluggability (rationale).
- ADR 0005 — Sandboxed Executor protocol (the executor field).
- `plato/domain/__init__.py` — `DOMAIN_REGISTRY` + `register_domain` +
  `get_domain` + `list_domains`.
