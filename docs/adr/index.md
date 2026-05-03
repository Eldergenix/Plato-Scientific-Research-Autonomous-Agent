# Architecture Decision Records

This directory holds the design decisions Plato lives with — one
markdown file per decision, named `NNNN-slug.md` and kept short.
Each ADR captures the **context** that motivated the choice, the
**decision** itself, and the **consequences** the team accepts.

ADRs are append-only. When a decision is revised, write a new ADR
that supersedes the old one and link both.

## Index

| #  | Status        | Title |
|----|---------------|-------|
| 0001 | Accepted    | [LangGraph as the default backend](0001-langgraph-as-default-backend.md) |
| 0002 | Accepted    | [Postgres checkpointer](0002-postgres-checkpointer.md) |
| 0003 | Accepted    | [Domain profile pluggability](0003-domain-profile-pluggability.md) |
| 0004 | Accepted    | [X-Plato-User multi-tenancy](0004-x-plato-user-multi-tenancy.md) |
| 0005 | Accepted    | [Sandboxed Executor protocol](0005-sandboxed-executor-protocol.md) |

## How to add an ADR

1. Pick the next free number (e.g. `0006`).
2. Copy an existing ADR file as a template.
3. Fill in **Status / Date / Deciders / Phase / Context / Decision /
   Consequences / See also**.
4. Add a row to the table above.
5. Append the entry to `mkdocs.yml`'s `Architecture Decisions:` block
   so it appears in the docs nav.

## Why ADRs?

Code shows what we did; ADRs show why. When a future contributor
asks "why is the executor a Protocol instead of a base class?",
ADR 0005 answers in two paragraphs instead of forcing them to
spelunk git history.
