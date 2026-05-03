# Autonomous Research Loop

> R10. Run Plato unattended under a wall-clock and cost budget. Each
> iteration scores the project against citation validity, unsupported
> claims, referee severity, and lines-of-code drift. Improvements are
> committed to a tracking branch; regressions are reverted.

The loop is the practical unlock for "leave it overnight, wake up to a
refined paper." Backed by `plato/loop/research_loop.py`.

## Quick start

```bash
plato loop \
  --project-dir ./my_project \
  --hours 8 \
  --max-cost-usd 50 \
  --max-iters 20 \
  --branch-prefix plato-runs
```

The loop will:

1. Open a per-loop tracking branch (`plato-runs/<timestamp>`) inside
   the project repo.
2. Run the full Plato pipeline once per iteration.
3. Score the result via `AcceptanceScore.composite` (citation rate,
   unsupported-claim rate, referee severity, LOC drift).
4. `git commit` and tag accepted iterations; `git reset --hard HEAD`
   discarded ones.
5. Stop when any of the budget caps fires (time, max-iters, cost).

## Acceptance score

```
composite = citation_validation_rate
          - unsupported_claim_rate
          - 0.1  * referee_severity_max
          - 0.001 * simplicity_delta
```

Higher is better. The constants are intentionally simple — the goal is
a single comparable scalar, not a tuned reward function. The
`simplicity_delta` term penalises iterations that ship more LaTeX
without proportional citation gains, biasing the loop toward concise
revisions.

## Budgets and safety

- `--hours` caps wall-clock. Default 8.
- `--max-cost-usd` caps cumulative LLM spend across iterations.
  Default 50. Cost data flows from the run manifest's `cost_usd`
  field, populated by the iter-8 ManifestCallbackHandler (R8).
- `--max-iters` caps iteration count.
- `--simplicity-bias` adjusts the LOC-drift weight (default 0.001).
- SIGINT (Ctrl-C) writes an "interrupted" row to the TSV log and
  exits cleanly without corrupting git state.

## Output

Every loop produces:

- `runs.tsv` — append-only per-iteration log:
  `iter\ttimestamp\tcomposite\tstatus\tdescription`
- A git branch `plato-runs/<timestamp>` with one commit per accepted
  iteration.
- `manifest.json` per iteration under `project_dir/runs/<run_id>/`
  with the full reproducibility record (model versions, git sha,
  source ids, prompt hashes, tokens, cost).

## Observability

When `LANGFUSE_*` env vars are set, every iteration's LLM calls flow
into the same Langfuse session id (the loop's `loop_id`), grouping
nightly traces in the Langfuse dashboard.

## See also

- ADR 0005 — Sandboxed Executor protocol (tracks how `get_results()`
  becomes safe to run inside the loop without a host-side sandbox).
- `dashboard/frontend/src/app/loop/page.tsx` — the dashboard's
  loop monitor.
