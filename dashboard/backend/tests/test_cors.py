"""CORS preflight assertions for the dashboard API.

We don't trust ``allow_*=*`` defaults; production runs the dashboard
behind a CORS-aware proxy and the browser will refuse a credentialed
request that doesn't see explicit allowlists. These tests pin the
allow-methods, allow-headers, and origin allowlist so a future setting
change can't silently regress to wildcards.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _options(client: TestClient, path: str, origin: str, *, method: str = "GET", headers: str | None = None):
    """Issue a CORS preflight request and return the response."""
    request_headers = {
        "Origin": origin,
        "Access-Control-Request-Method": method,
    }
    if headers is not None:
        request_headers["Access-Control-Request-Headers"] = headers
    return client.options(path, headers=request_headers)


def test_preflight_returns_explicit_allow_methods(client: TestClient) -> None:
    """OPTIONS preflight must list real verbs, never the ``*`` wildcard.

    Wildcard methods are incompatible with credentialed requests and
    silently break the SPA when the dashboard is hit from a different
    origin. We pin a representative subset to catch regressions.
    """
    resp = _options(client, "/api/v1/health", "http://localhost:3000")
    assert resp.status_code in (200, 204)

    raw = resp.headers.get("access-control-allow-methods", "")
    assert raw, f"missing access-control-allow-methods header: {dict(resp.headers)!r}"
    assert raw.strip() != "*", f"allow-methods returned wildcard: {raw!r}"

    methods = {m.strip().upper() for m in raw.split(",")}
    for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
        assert verb in methods, f"missing {verb} in allow-methods: {methods!r}"


def test_preflight_omits_origin_header_for_disallowed_origin(
    client: TestClient,
) -> None:
    """An origin outside ``settings.cors_origins`` must NOT be echoed back.

    Starlette's CORSMiddleware silently drops the ACAO header for an
    unknown origin (it doesn't 4xx), so we assert the absence of the
    header rather than a status code.
    """
    resp = _options(
        client,
        "/api/v1/health",
        origin="https://attacker.example",
    )
    # Either 400 (when an explicit allowlist rejects) or 200/204; what
    # matters is that the browser cannot infer the origin is allowed.
    acao = resp.headers.get("access-control-allow-origin")
    assert acao != "https://attacker.example", (
        f"disallowed origin echoed back: {acao!r}"
    )
    # And we never silently widen to a wildcard with credentials.
    assert acao != "*", "wildcard origin returned with credentials"


def test_simple_get_reflects_allowed_origin_only(client: TestClient) -> None:
    """A non-preflight GET must echo only origins on the allowlist.

    Browsers also honor CORS on the *actual* request, not just the
    preflight. We hit a real endpoint (no OPTIONS) with two origins —
    the dev origin should be reflected, an attacker origin must not —
    and never as a wildcard.
    """
    allowed = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert allowed.status_code == 200
    acao = allowed.headers.get("access-control-allow-origin")
    assert acao == "http://localhost:3000", (
        f"expected echoed origin, got {acao!r}"
    )

    rejected = client.get(
        "/api/v1/health",
        headers={"Origin": "https://attacker.example"},
    )
    # The endpoint still responds (CORS is browser-enforced), but the
    # ACAO header must NOT advertise the bad origin.
    bad_acao = rejected.headers.get("access-control-allow-origin")
    assert bad_acao != "https://attacker.example"
    assert bad_acao != "*", "wildcard ACAO leaked on a credentialed-style fetch"


def test_preflight_advertises_x_plato_user_in_allow_headers(
    client: TestClient,
) -> None:
    """X-Plato-User must round-trip through the preflight allow-headers.

    The frontend sends this header on every authenticated fetch; if
    CORS strips it the browser blocks the call before it reaches the
    auth middleware.
    """
    resp = _options(
        client,
        "/api/v1/projects",
        origin="http://localhost:3000",
        method="GET",
        headers="X-Plato-User",
    )
    assert resp.status_code in (200, 204)

    raw = resp.headers.get("access-control-allow-headers", "")
    assert raw, f"missing access-control-allow-headers header: {dict(resp.headers)!r}"
    headers = {h.strip().lower() for h in raw.split(",")}
    assert "x-plato-user" in headers, (
        f"X-Plato-User missing from allow-headers: {headers!r}"
    )
