# Architecture Overview

> A landing page for new contributors. The seven [ADRs](adr/index.md)
> document specific decisions; this page wires them together so you
> can see how a topic becomes a paper without reading every file.

## What is Plato?

Plato is an autonomous research agent: feed it a topic and a project
folder, and it produces a conference-ready paper with real citations,
executed experiments, multi-axis peer review, and a reproducibility
manifest. Under the hood it is a pair of LangGraph state machines
sharing a project directory — one graph runs ideation and literature
work, the other drafts, reviews, and exports the paper. Everything
domain-shaped (retrieval source, executor, journal style, keyword
extractor) is a registry swap point, so the same engine drives astro,
biology, ML, or any domain a user registers.

## The two-tier graph

Two graphs, two state types, one filesystem. The first tier
(`plato/langgraph_agents/agents_graph.py:27`) reasons about the idea
and the literature. The second tier
(`plato/paper_agents/agents_graph.py:85`) authors the paper.

```mermaid
flowchart TD
    subgraph T1["Tier 1: langgraph_agents (ideation)"]
        P1[preprocess] --> CLR[clarifier]
        CLR --> MK[idea_maker]
        MK -->|critique loop| HT[idea_hater]
        HT --> MK
        P1 --> NV[novelty_decider]
        NV --> SS[semantic_scholar / SLR]
        SS --> NV
        NV --> LS[literature_summary]
        LS --> CE[counter_evidence]
        CE --> GD[gap_detector]
    end

    subgraph T2["Tier 2: paper_agents (authoring)"]
        P2[preprocess] --> KW[keywords]
        KW --> AB[abstract] --> IN[introduction] --> ME[methods]
        ME --> RS[results] --> CN[conclusions] --> PL[plots]
        PL --> RF[refine_results] --> CT[citations]
        CT --> CV[citation_validator] --> CX[claim_extractor]
        CX --> EM[evidence_matrix] --> RP{reviewer panel}
        RP -->|methodology| AGG[critique_aggregator]
        RP -->|statistics| AGG
        RP -->|novelty| AGG
        RP -->|writing| AGG
        AGG -->|severity gate| RD[redraft]
        RD --> RP
    end

    T1 -.->|state['files']['Folder']| T2
```

Tier 1 also fans into a visual `referee` node and an `methods_fast`
shortcut; Tier 2's reviewer fan-out runs the four reviewers in
parallel and only redrafts if `critique_aggregator` raises a severity
flag below the iteration cap. See ADR 0001 for why LangGraph is the
default.

## Extension registries

Six registries make Plato pluggable without forking. ADR 0003 is the
canonical reference; each registry lives next to the protocol it
implements.

| Registry | Module | Add a new one when… |
|---|---|---|
| `DomainProfile` | `plato/domain/__init__.py:46` | You want a one-line bundle of the five other registries (e.g. `biology`). |
| `Tool` | `plato/tools/registry.py` | You ship a callable an agent should be able to invoke. |
| `SourceAdapter` | `plato/retrieval/__init__.py:38` | A new literature backend (PubMed, ADS, a private corpus). |
| `JournalPreset` | `plato/journal_preset/__init__.py` | A new venue style (margins, bib format, keyword schema). |
| `KeywordExtractor` | `plato/keyword_extractor/__init__.py` | The default extractor doesn't fit your taxonomy (MeSH, OpenAlex concepts). |
| `Executor` | `plato/executor/__init__.py:73` | A new code-execution backend (Modal, e2b, local Jupyter). See ADR 0005. |

A third-party plug-in registers itself on import — drop a
`register_*(...)` call in your package's `__init__.py` and the entry
shows up in the dashboard's domain picker.

## State, manifests, and run reproducibility

Each tier has its own `GraphState` TypedDict
(`plato/langgraph_agents/parameters.py:79`,
`plato/paper_agents/parameters.py`) that bundles `messages`, the
`FILES` map, `LLM` configs, `IDEA`/`LITERATURE` substates, and an
opaque `recorder` slot for telemetry.

- **Checkpointer.** `make_checkpointer()`
  (`plato/state/checkpointer.py:54`) defaults to a SQLite WAL store at
  `~/.plato/state.db`. ADR 0002 covers the Postgres opt-in for
  multi-tenant deployments.
- **Manifest.** Every workflow opens a `RunManifest`
  (`plato/state/manifest.py`) at
  `<project>/runs/<run_id>/manifest.json`. Fields: `git_sha`,
  `prompt_hashes`, `models`, `seeds`, `cost_usd`, `tokens_per_node`,
  `source_ids`, `user_id`. Flushes are idempotent so a crash leaves a
  partial-but-useful manifest.
- **Per-node telemetry.** `LLM_call`/`LLM_call_stream` thread the
  active node name through to `tokens_per_node` so the dashboard can
  attribute cost. `prompt_hashes` is updated by
  `paper_agents/tools.py:31` whenever a node renders a prompt — flip
  one prompt and the manifest tells you which node moved.

## Safety and multi-tenancy

ADR 0004 makes the dashboard proxy-trusting: the reverse proxy sets
`X-Plato-User`, the dashboard scopes everything under `users/<id>/`,
and `_enforce_run_tenant()` (`dashboard/backend/src/plato_dashboard/api/server.py`)
cross-checks every run access against the manifest's `user_id`.
`X-Plato-Run-Id` (server.py:329) correlates per-request logs with the
LangGraph thread id.

Two more layers sit below the header:

- **File scope.** `scoped_node(fn, scope)` (`plato/io/scoped_node.py`)
  wraps every node that writes a file so paths are rooted at
  `state["files"]["Folder"]`. An LLM-generated `../../../etc/passwd`
  raises `ScopeError` instead of escaping the project. Both graphs
  use this — see the `scoped_node(...)` calls in
  `agents_graph.py:53-69` (Tier 1) and `agents_graph.py:115-145`
  (Tier 2).
- **Prompt-injection wrapping.** External text (paper bodies, web
  responses, evidence packs) goes through `wrap_external()`
  (`plato/safety/sanitize.py`) before it reaches an LLM. Examples:
  `plato/plato.py:545`, `paper_agents/evidence_matrix_node.py:74`,
  `paper_agents/prompts.py:53`.

## Dashboard surface

- **Backend.** FastAPI app at
  `dashboard/backend/src/plato_dashboard/api/server.py:380` mounts
  ~22 routers under `/api/v1` covering runs, manifests, citations,
  evals, telemetry, retrieval, novelty signals, license audit,
  clarifications, critiques, domains, executors and their
  preferences, the autonomous loop, run presets, user preferences,
  and an auth probe. Live run output streams over SSE.
- **Frontend.** Next.js App Router in
  `dashboard/frontend/src/app/`. Top-level routes: `runs/`,
  `loop/`, `evals/`, `costs/`, `models/`, `keys/`, `projects/`,
  `activity/`, and `settings/`. The runs route nests
  `[runId]/{citations,clarify,literature,research,reviews}` so each
  detail panel maps to the matching backend router.

## Skills and external integrations

The `.claude/skills/` directory bundles nine Claude Code skills (see
the precedence rules in [CLAUDE.md §10](../CLAUDE.md)). For
researchers who want a fully autonomous run, the
`autoresearchclaw-autonomous-research` skill plugs in at the top of
the pipeline; ADR 0006 maps its 23 stages onto the two-tier graph and
flags the four gaps (stages 13, 15, 16, 20). New external skills slot
in either as new entry points on `Plato` (top-level workflow
methods), as new nodes inside a tier graph, or as new dashboard
routers — pick the layer that matches the skill's scope.

## Where to start

- **"I want to add a new domain."** Add a `register_domain(...)` call
  for your `DomainProfile`; see `plato/domain/__init__.py` and the
  recipe in [Domain Pluggability](features/domain-pluggability.md).
- **"I want to add a new section to the paper."** Add a node in
  `plato/paper_agents/agents_graph.py:115`, define its scope in
  `plato/paper_agents/scopes.py`, and slot it into the linear chain
  starting at `keywords_node`. Wrap with `scoped_node` if it writes
  files.
- **"I want to add a dashboard panel."** Add a router under
  `dashboard/backend/src/plato_dashboard/api/`, mount it in
  `server.py:388`, and add a Next.js page under
  `dashboard/frontend/src/app/`. The existing `runs/[runId]/`
  pages are the closest reference for SSE-driven detail panels.

## See also

- [ADR 0001](adr/0001-langgraph-as-default-backend.md) — why LangGraph.
- [ADR 0002](adr/0002-postgres-checkpointer.md) — durable state.
- [ADR 0003](adr/0003-domain-profile-pluggability.md) — registries.
- [ADR 0004](adr/0004-x-plato-user-multi-tenancy.md) — auth model.
- [ADR 0005](adr/0005-sandboxed-executor-protocol.md) — executor protocol.
- [ADR 0006](adr/0006-autoresearchclaw-stage-mapping.md) — skill mapping.
- [ADR 0007](adr/0007-known-deferred-work.md) — open work register.
