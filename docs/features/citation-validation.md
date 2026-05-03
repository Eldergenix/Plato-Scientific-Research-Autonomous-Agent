# Citation Validation

> R3. Per-reference Crossref + Retraction Watch + arXiv resolution
> producing `validation_report.json` per run.

## What it does

For every reference cited in a finished paper, the
`citation_validator_node` checks:

- **DOI resolution** — `https://api.crossref.org/works/{doi}`
  returns 200? Metadata extracted into `ValidationResult.title`.
- **Retraction status** — Crossref's `update-to` field signals
  retractions; an optional Retraction Watch CSV (passed via the
  `CitationValidator(retraction_db=...)` constructor) provides a
  fallback DOI-set lookup.
- **arXiv aliveness** — `https://export.arxiv.org/abs/{id}`
  returns 200? `withdrawn` flag detected.
- **URL liveness** — for refs with neither DOI nor arxiv id, the
  fallback URL is HEAD-checked.

Results land at
`<project_dir>/runs/<run_id>/validation_report.json` with fields:

```json
{
  "run_id": "abc123",
  "validation_rate": 0.85,
  "total": 20,
  "passed": 17,
  "unverified_count": 3,
  "failures": [
    {"source_id": "...", "reason": "doi_404", "doi": "..."},
    {"source_id": "...", "reason": "retracted", "doi": "..."}
  ]
}
```

The dashboard `/runs/[runId]` page renders this via
`ValidationReportCard` with search / group-by-reason / copy-CSV
controls.

## Where it runs in the paper graph

```
... → citations_node → citation_validator_node → claim_evidence_fanout
```

Wired in `plato/paper_agents/agents_graph.py`. The validator runs
before the claim-extraction + evidence-matrix sequence so failed
references can be flagged in the reviewer panel's grounding axis.

## Persistence

When a SQL `Store` is in scope (`state["store"]`), each
`ValidationResult` is also persisted via `Store.add_validation`.
Otherwise only the JSON sidecar is written.

## See also

- `plato/tools/citation_validator.py` — the async validator.
- `plato/paper_agents/citation_validator_node.py` — the LangGraph
  node wrapper.
- `tests/unit/test_citation_validator.py` — 11 tests covering DOI
  hits, hallucinated DOIs, retracted DOIs, dead URLs, batch
  concurrency, and async context-manager lifecycle.
