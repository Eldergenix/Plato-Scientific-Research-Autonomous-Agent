# Reviewer Panel + Revision Loop

> R6. Four-axis reviewer panel runs after the citations node and
> drives a bounded redraft loop until critiques are addressed or the
> iteration cap is hit.

## Axes

| Axis         | What it grades                              |
|--------------|---------------------------------------------|
| methodology  | Statistical design, experimental validity   |
| statistics   | Numerical claims, error bars, sig tests     |
| novelty      | What's actually new vs. derivative          |
| writing      | Clarity, structure, prose flow              |

Each axis is an independent LangGraph node, fanned out in parallel
after `citations_node`:

```
citations_node
   ↓
reviewer_panel_fanout
   ├─ methodology_reviewer
   ├─ statistics_reviewer
   ├─ novelty_reviewer
   └─ writing_reviewer
       ↓
critique_aggregator
   ↓
revision_router → redraft_node (loop) | END
```

Each reviewer emits `{severity: 0..5, issues: [...], rationale: str}`
into `state["critiques"][axis]`. The aggregator builds a digest
with `max_severity` across axes and stores
`state["critique_digest"]`.

## Redraft loop

`revision_router` (`plato/paper_agents/routers.py`) picks
`redraft_node` when `max_severity > 2 AND iteration < max_iterations`,
else `END`. The default `max_iterations` is 2 — exposed as
`Plato.get_paper(max_revision_iters=...)` since iter 5.

`redraft_node` rewrites the paper sections with the critique
digest in scope, then bumps `revision_state["iteration"]`. The
loop is guaranteed to terminate because the iteration counter
monotonically increases and the cap is enforced unconditionally.

## Reading from the dashboard

Critique payloads are also persisted to `<run_dir>/critiques.json`
and surfaced via:

- `GET /api/v1/runs/{run_id}/critiques` — canonical endpoint
- `GET /api/v1/runs/{run_id}/reviews` — alias for parity with the
  architectural-plan naming (added iter 6)

Both serve the same `{critiques, digest, revision_state}` payload.
The frontend `/runs/[runId]/reviews` page renders a per-axis card
plus the current iteration counter.

## Anti-self-grading safeguard

Each reviewer uses a different model from the drafting model —
`Plato.get_paper` accepts a `judge_models` parameter and refuses
to start when the drafting model is in the panel. Same guard
that the eval harness's `LLMJudge` enforces.

## See also

- `plato/paper_agents/reviewer_panel.py` — 4 reviewer node
  factories.
- `plato/paper_agents/critique_aggregator.py` — digest model +
  aggregation logic.
- `plato/paper_agents/redraft_node.py` — single-pass redraft.
