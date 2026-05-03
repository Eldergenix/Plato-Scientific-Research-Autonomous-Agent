# Multi-Tenant Auth via X-Plato-User

> ADR 0004. The dashboard scopes every project / key store / run
> manifest / validation report to the requester's user id. Identity
> is delegated to an upstream proxy.

## Quick start

Single-user (default — no setup):

```bash
plato dashboard
```

Multi-tenant:

```bash
export PLATO_DASHBOARD_AUTH_REQUIRED=1
plato dashboard
```

In multi-tenant mode every request must carry `X-Plato-User: <id>`.
Missing or invalid headers return 401.

## Why the header pattern

Plato deliberately doesn't own identity:

- Customers usually have an SSO they want to integrate with
  (Cloudflare Access, oauth2-proxy, traefik-forward-auth, Keycloak).
- Building yet another login flow would either duplicate or
  conflict with that.
- The proxy already authenticates the user; it just needs a way
  to tell Plato who the request belongs to.

So the contract is:

1. Proxy authenticates the user against the real IdP.
2. Proxy sets `X-Plato-User: <id>` on every request to the dashboard.
3. The proxy must strip any client-supplied `X-Plato-User` before
   rewriting it (otherwise a client can spoof the id directly).
4. The dashboard validates the value against
   `[A-Za-z0-9._-]{1,64}` and uses it as a path segment under
   `<project_root>/users/<user_id>/`.

## What's scoped

| Surface               | Scoped how                                      |
|-----------------------|-------------------------------------------------|
| Project store         | `<project_root>/users/<id>/projects/<pid>/`     |
| Key store             | `~/.plato/keys.json` (per-process today; may move per-user) |
| Run manifests         | manifest's `user_id` field; cross-tenant reads → 403 |
| Validation reports    | `_enforce_run_tenant` on every read             |
| Evidence matrix       | same enforcement                                |
| Critiques             | same enforcement                                |
| Loop registry         | `loop_id` namespaced per-tenant in memory       |

## Run-id correlation

Every request carries `X-Plato-Run-Id` (from iter 13's frontend
hook) so log records correlate end-to-end across the proxy →
backend → worker → LangChain stack. Combined with `X-Plato-User`,
operators can pivot the same logs by user OR by run.

## Security review

`SECURITY.md` documents the four trust boundaries (LLM-generated
code execution, retrieved external text, user-uploaded PDFs,
dashboard authentication). 15 adversarial bypass tests live at
`tests/safety/test_dashboard_auth_bypass.py` covering:

- empty / whitespace-only header values
- CRLF injection attempts
- cookie smuggling
- query-string forgery
- path-traversal id values

## See also

- ADR 0004 — X-Plato-User multi-tenancy (rationale + threat model).
- `plato_dashboard/auth.py` — `extract_user_id`, `require_user_id`,
  the `_USER_ID_RE` validator.
- `plato_dashboard/api/server.py` — `_enforce_run_tenant` and the
  middleware stack that binds `run_id_var` from `X-Plato-Run-Id`.
