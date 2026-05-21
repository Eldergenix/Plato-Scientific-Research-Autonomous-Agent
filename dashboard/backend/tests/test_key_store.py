"""Smoke tests for the encrypted KeyStore."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plato_dashboard.api.server import create_app
from plato_dashboard.auth import AUTH_REQUIRED_ENV
from plato_dashboard.domain.models import KeysPayload
from plato_dashboard.storage.key_store import ENV_KEYS, KeyStore


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    ks = KeyStore(tmp_path / "keys.json")
    ks.save(KeysPayload(OPENAI="sk-aaaa", ANTHROPIC="sk-bbbb"))

    loaded = ks.load()
    assert loaded.OPENAI == "sk-aaaa"
    assert loaded.ANTHROPIC == "sk-bbbb"
    assert loaded.GEMINI is None


def test_save_does_not_overwrite_existing_keys_with_none(tmp_path: Path) -> None:
    """Partial updates merge — None fields don't clobber stored values."""
    ks = KeyStore(tmp_path / "keys.json")
    ks.save(KeysPayload(OPENAI="sk-old", GEMINI="g-old"))

    # Update only Anthropic; the others should be preserved.
    ks.save(KeysPayload(ANTHROPIC="ant-new"))

    loaded = ks.load()
    assert loaded.OPENAI == "sk-old"
    assert loaded.GEMINI == "g-old"
    assert loaded.ANTHROPIC == "ant-new"


def test_env_var_takes_precedence_over_in_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ks = KeyStore(tmp_path / "keys.json")
    ks.save(KeysPayload(OPENAI="sk-in-app"))

    monkeypatch.setenv(ENV_KEYS["OPENAI"], "sk-from-env")
    assert ks.resolve("OPENAI") == "sk-from-env"

    monkeypatch.delenv(ENV_KEYS["OPENAI"], raising=False)
    assert ks.resolve("OPENAI") == "sk-in-app"


def test_status_reflects_which_keys_are_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Start clean: no env vars set.
    for env_var in ENV_KEYS.values():
        monkeypatch.delenv(env_var, raising=False)

    ks = KeyStore(tmp_path / "keys.json")
    ks.save(KeysPayload(OPENAI="sk-app", GEMINI="g-app"))
    monkeypatch.setenv(ENV_KEYS["ANTHROPIC"], "ant-from-env")

    status = ks.status()
    assert status.OPENAI == "in_app"
    assert status.GEMINI == "in_app"
    assert status.ANTHROPIC == "from_env"
    assert status.PERPLEXITY == "unset"
    assert status.SEMANTIC_SCHOLAR == "unset"


def test_keys_api_scopes_in_app_keys_by_lab_tenant(
    tmp_project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_var in ENV_KEYS.values():
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "1")

    with TestClient(create_app()) as client:
        saved = client.put(
            "/api/v1/keys",
            json={"OPENAI": "sk-lab"},
            headers={"X-Plato-User": "lab_org_alpha"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["OPENAI"] == "in_app"

        lab = client.get(
            "/api/v1/keys/status",
            headers={"X-Plato-User": "lab_org_alpha"},
        )
        personal = client.get(
            "/api/v1/keys/status",
            headers={"X-Plato-User": "user_scientist_a"},
        )

    assert lab.status_code == 200
    assert personal.status_code == 200
    assert lab.json()["OPENAI"] == "in_app"
    assert personal.json()["OPENAI"] == "unset"
    assert (tmp_project_root / "users" / "lab_org_alpha" / "keys.json").is_file()


def test_worker_resolves_keys_from_project_tenant_store(
    tmp_project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_var in ENV_KEYS.values():
        monkeypatch.delenv(env_var, raising=False)

    from plato_dashboard.worker import run_manager

    lab_keys = tmp_project_root / "users" / "lab_org_alpha" / "keys.json"
    KeyStore(lab_keys).save(KeysPayload(OPENAI="sk-lab-worker"))
    KeyStore(tmp_path / "global-keys.json").save(KeysPayload(OPENAI="sk-global"))

    project_dir = tmp_project_root / "users" / "lab_org_alpha" / "proj_123"
    project_dir.mkdir(parents=True)

    resolved = run_manager._resolve_keys(project_dir)

    assert resolved["OPENAI_API_KEY"] == "sk-lab-worker"
