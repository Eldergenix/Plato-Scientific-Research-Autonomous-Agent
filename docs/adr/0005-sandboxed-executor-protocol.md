# ADR 0005 — Sandboxed `Executor` protocol for `get_results()`

- **Status**: Accepted (interface) / In progress (sandbox)
- **Date**: 2026-04-30
- **Deciders**: Plato maintainers
- **Phase**: 5 (Production hardening)

## Context

`Plato.get_results()` runs LLM-generated code against the user's data.
Today that code executes in the host Python process via the cmbagent
executor — there is no seccomp container, no namespace isolation, no
network egress firewall. For a single-user desktop install that is
acceptable; for any multi-tenant deployment it is not.

ADR 0001 narrowed cmbagent to `get_results()` only. That decision left
open the question: how do we replace the executor without rewriting
every caller, and how do we do it incrementally?

## Decision

Express the executor surface as a `@runtime_checkable Protocol` with a
single async method, and route every `get_results()` call through a
registry keyed by name:

```python
@runtime_checkable
class Executor(Protocol):
    name: str

    async def run(
        self,
        *,
        project_dir: Path,
        keys: KeyManager,
        models: dict[str, str],
        cancel_event: asyncio.Event | None = None,
    ) -> ExecutorResult: ...

EXECUTOR_REGISTRY: dict[str, Executor] = {}
def get_executor(name: str) -> Executor: ...
```

A `DomainProfile` selects which executor `get_results()` dispatches to
(see ADR 0003). The factory functions for each backend live under
`plato/executor/`:

- `cmbagent.py` — runs in-process via the cmbagent library
  (legacy default; the **non-sandboxed** path).
- `local_jupyter.py` — out-of-process kernel via `jupyter_client`.
- `modal_backend.py` — Modal Functions container.
- `e2b_backend.py` — E2B sandbox.

The latter three are registered as **stubs** today (raise
`NotImplementedError`) so the contract is exercised end-to-end and
the dashboard can show the choice in `/settings/executors`.

## Consequences

**Positive.**

- The executor choice becomes a configuration surface, not a code
  surface. A non-astro deployment can register a custom backend
  without touching `Plato`.
- Migrating `get_results()` to a sandboxed default becomes a
  single change in the astro `DomainProfile` once a real backend
  lands.
- The Protocol is lightweight enough that test fixtures can stand
  in for the real implementation.

**Negative.**

- Until a real out-of-process backend lands, `get_results()` keeps
  the in-process gap that `SECURITY.md §"LLM-generated code
  execution"` calls out. The Protocol is necessary but not
  sufficient.
- Async-only `run()` forces every backend to integrate with
  `asyncio` even when the underlying SDK is sync.

**Neutral.**

- Executor implementations vary widely in startup cost (cmbagent
  in-process is sub-millisecond; Modal/e2b are seconds). Callers
  that want fast iteration should prefer `cmbagent` until a fast
  sandboxed alternative exists.

## Implementation status

| Backend          | Status        | Sandbox | Notes                                  |
| ---------------- | ------------- | ------- | -------------------------------------- |
| `cmbagent`       | Implemented   | None    | Legacy default; in-process             |
| `local_jupyter`  | Stub          | Process | Needs `jupyter_client` kernel loop     |
| `modal`          | Stub          | Container | Needs Modal SDK integration         |
| `e2b`            | Stub          | Container | Needs E2B SDK integration           |

The `EXECUTOR_REGISTRY` is populated at import time in
`plato/executor/__init__.py:102-104`. Tests in
`tests/unit/test_executor_registry.py` cover registration, name
collision, and unknown-backend handling. Tests in
`dashboard/backend/tests/test_executors_api.py` cover the dashboard
view layer.

## See also

- ADR 0003 — DomainProfile pluggability (which `executor` field this
  protocol satisfies).
- `SECURITY.md` §"LLM-generated code execution" for the threat model
  this ADR is the long-term answer to.
