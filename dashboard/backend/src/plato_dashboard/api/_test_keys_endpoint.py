"""Smoke test for ``POST /api/v1/keys/test/{provider}``.

Run from inside the dashboard backend venv::

    python -m plato_dashboard.api._test_keys_endpoint

This does NOT call any provider APIs (that requires real keys). It just
spins up an in-process FastAPI client, points the key store at an empty
temp dir, and verifies the endpoint reports ``ok=false, error="no key
configured"`` when no key is set, plus 400 for unknown providers.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> int:
    # Point the key store at an empty temp dir so we never touch the real
    # ~/.plato/keys.json.
    tmp = Path(tempfile.mkdtemp(prefix="plato-keytest-"))
    os.environ["PLATO_KEYS_PATH"] = str(tmp / "keys.json")
    os.environ["PLATO_PROJECT_ROOT"] = str(tmp / "projects")
    os.environ["PLATO_DEMO_MODE"] = "disabled"
    # Make sure no real provider keys leak in from the host environment.
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "PERPLEXITY_API_KEY",
        "SEMANTIC_SCHOLAR_KEY",
    ):
        os.environ.pop(env_var, None)

    # Force a fresh Settings() — the dashboard caches per-import.
    from plato_dashboard import settings as _settings

    _settings.get_settings.cache_clear() if hasattr(
        _settings.get_settings, "cache_clear"
    ) else None

    from fastapi.testclient import TestClient

    from plato_dashboard.api.server import create_app

    app = create_app()
    client = TestClient(app)

    failures: list[str] = []

    # 1. Route is wired up at the expected path.
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    if "/api/v1/keys/test/{provider}" not in paths:
        failures.append(
            "expected route /api/v1/keys/test/{provider} not registered; "
            f"have: {sorted(p for p in paths if 'keys' in p)}"
        )

    # 2. Each provider returns ok=false, error="no key configured".
    for provider in ("OPENAI", "GEMINI", "ANTHROPIC", "PERPLEXITY", "SEMANTIC_SCHOLAR"):
        resp = client.post(f"/api/v1/keys/test/{provider}")
        if resp.status_code != 200:
            failures.append(f"{provider}: expected 200, got {resp.status_code} {resp.text}")
            continue
        body = resp.json()
        if set(body.keys()) != {"ok", "latency_ms", "error"}:
            failures.append(f"{provider}: unexpected keys in response: {sorted(body)}")
        if body.get("ok") is not False:
            failures.append(f"{provider}: expected ok=false, got {body.get('ok')!r}")
        if body.get("error") != "no key configured":
            failures.append(
                f"{provider}: expected error='no key configured', got {body.get('error')!r}"
            )
        if not isinstance(body.get("latency_ms"), int):
            failures.append(
                f"{provider}: expected int latency_ms, got {type(body.get('latency_ms')).__name__}"
            )

    # 3. Unknown provider yields 400.
    resp = client.post("/api/v1/keys/test/BOGUS")
    if resp.status_code != 400:
        failures.append(f"BOGUS: expected 400, got {resp.status_code} {resp.text}")

    if failures:
        print("FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("OK — /api/v1/keys/test/{provider} returns the expected shape for all providers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
