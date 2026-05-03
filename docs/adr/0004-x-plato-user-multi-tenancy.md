# ADR 0004 — Multi-tenant dashboard via the `X-Plato-User` header

- **Status**: Accepted
- **Date**: 2026-04-30
- **Deciders**: Plato maintainers
- **Phase**: 5 (Production hardening)

## Context

Phase 5 of the architectural plan called for the dashboard to support
multiple users without forking the codebase. The challenge:

- Plato itself is a stateless library that writes into a project
  directory; per-user isolation is a deployment concern.
- The dashboard does **not** want to own identity. The right place
  for an IdP integration is a reverse proxy (Cloudflare Access,
  oauth2-proxy, traefik-forward-auth) — that's where customers
  already plug in SSO.
- We still need a way for the proxy to tell the dashboard "this
  request belongs to alice" so the project store, run manifests, and
  validation reports can scope correctly.

## Decision

Treat the dashboard as **proxy-trusting** and read the user id from
a single header: **`X-Plato-User`**.

The contract is:

1. The proxy authenticates the user against the real IdP and sets
   `X-Plato-User: <user-id>` on every request to the dashboard.
2. The dashboard never tries to validate the IdP itself. The header
   is the trust anchor.
3. `extract_user_id(request)` rejects header values that don't match
   `[A-Za-z0-9._-]{1,64}` so a malicious value can't be smuggled
   into a filesystem path.
4. When `PLATO_DASHBOARD_AUTH_REQUIRED=1`, every request must carry
   a valid header. Missing/invalid → `401`.
5. When `PLATO_DASHBOARD_AUTH_REQUIRED` is unset, the dashboard
   stays single-user — backwards-compatible with every existing
   self-hosted install.

The user id is used as a path segment under
`<project_root>/users/<user_id>/`, namespacing the project store,
key store, executor preferences, domain preferences, run manifests,
and (eventually) Postgres rows.

`_enforce_run_tenant()` (in `dashboard/backend/.../api/server.py`)
cross-checks every run access against the manifest's `user_id`
field, so a tenant cannot read another tenant's run even if they
guess the run id.

## Consequences

**Positive.**

- The dashboard ships with zero auth code paths beyond the header
  check, keeping the attack surface tiny.
- Users can deploy any IdP they already operate.
- Single-user deployments don't pay the multi-tenant complexity tax.

**Negative.**

- The dashboard must be deployed behind a proxy in any production
  setting. Exposing it directly to the internet would let any
  client set `X-Plato-User` themselves — the dashboard cannot
  detect this.
- Header injection at the proxy layer becomes a critical concern.
  The proxy must strip any client-supplied `X-Plato-User` before
  rewriting it.

**Neutral.**

- The user id format is opinionated — apps that want to use opaque
  emails or UUIDs need a small mapping layer at the proxy.

## Implementation

- `dashboard/backend/src/plato_dashboard/auth.py` defines
  `extract_user_id`, `require_user_id`, and the `USER_HEADER`
  constant.
- `_resolve_project_root()` in `api/server.py` namespaces the project
  store by `user_id`.
- `_enforce_run_tenant()` and `manifests._enforce_tenant()` cross-check
  the manifest's `user_id` field on every run-scoped read.
- `tests/safety/test_dashboard_auth_bypass.py` covers 15 bypass
  attempts (empty, whitespace, CRLF injection, cookie smuggling,
  query-string forgery).

## See also

- ADR 0001 — Single backend (LangGraph) — defines the surface area
  this header guards.
- `SECURITY.md` §"Dashboard authentication & authorization" for the
  full threat model.
