# ADR 0001 — LangGraph is the default backend; cmbagent is retained only for `get_results()`

- **Status**: Accepted
- **Date**: 2026-04-29
- **Deciders**: Plato maintainers
- **Phase**: 1 (Stabilize)

## Context

Before Phase 1, `Plato.get_idea()` and `Plato.get_method()` exposed two
backends through a `mode` parameter:

- `mode="fast"` — LangGraph state machine (`plato.langgraph_agents.*`).
- `mode="cmbagent"` — multi-agent orchestration via the
  [`cmbagent`](https://pypi.org/project/cmbagent/) library.

Maintaining both:

- doubled the test surface area;
- made the public API ambiguous (no clear default behaviour);
- coupled Plato to a vendor-specific orchestrator with limited
  observability.

Independently, `Plato.get_results()` and `Plato.get_keywords()` continue
to depend on `cmbagent`, which performs **code execution against
scientific data** — a capability that does not yet have a sandboxed
in-tree replacement.

## Decision

1. **LangGraph is the canonical backend** for idea generation, method
   generation, literature checking, paper drafting, and refereeing.
2. The `cmbagent` paths for **idea / method** are deprecated and will be
   removed once Phase 5's sandboxed `Executor` ships. Calls to
   `Plato.get_idea(mode='cmbagent')`, `Plato.get_idea_cmbagent`,
   `Plato.get_method(mode='cmbagent')`, and `Plato.get_method_cmbagent`
   emit `DeprecationWarning` from Phase 1 onward.
3. **`cmbagent` remains a hard dependency** for the time being, used
   exclusively by `Plato.get_results()` and `Plato.get_keywords()`. Both
   will move behind the pluggable `Executor` and `KeywordExtractor`
   interfaces (see §5.9 of the Phase-1 plan) in Phase 5.
4. New work targets the LangGraph backend only.

## Consequences

**Positive**

- One canonical workflow path simplifies docs, tests, and the dashboard.
- Phase 2 work (citation validation, retrieval, claim/evidence matrix)
  can target a single state model.
- Future executor backends (Modal, E2B, local Jupyter, etc.) plug in
  through the `Executor` registry without touching the `Plato` class.

**Negative**

- Existing scripts that call the cmbagent paths will see warnings until
  they migrate to `mode='fast'`.

**Neutral**

- `cmbagent` stays a hard dependency until Phase 5; `pyproject.toml`
  is unchanged.

## References

- Phase 1 plan: `~/.claude/plans/ultrathink-below-is-a-scalable-alpaca.md`
- Code: [plato/plato.py](../../plato/plato.py),
  [plato/langgraph_agents/agents_graph.py](../../plato/langgraph_agents/agents_graph.py),
  [plato/paper_agents/agents_graph.py](../../plato/paper_agents/agents_graph.py)
