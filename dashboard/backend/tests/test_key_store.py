"""Smoke tests for the encrypted KeyStore."""

from __future__ import annotations

from pathlib import Path

import pytest

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
