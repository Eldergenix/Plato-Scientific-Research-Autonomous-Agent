"""Per-role models and allowance weights (plato/scientist/models.py)."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from plato.scientist import models
from plato.scientist.llm import AnthropicScientistModel
from plato.scientist.schemas import FigureCritique

ROOT = Path(__file__).resolve().parents[2]


class _FakeMessages:
    """Records the last request; answers every stream with one fixed response."""

    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def stream(self, **kwargs):
        self.kwargs = kwargs
        return _FakeStream(self.response)


class _FakeStream:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self.response


def _response(parsed):
    # 100 in + 50 out + 10 cache read = 160 tokens per call.
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=10,
    )
    text = SimpleNamespace(type="text", text=parsed.model_dump_json())
    return SimpleNamespace(
        stop_reason="end_turn", content=[text], usage=usage, stop_details=None
    )


def test_worker_catalogue_matches_python():
    path = ROOT / "cloudflare/plato-scientist/src/models.json"
    assert json.loads(path.read_text("utf-8")) == models.catalogue()


def test_defaults_opus_orchestrator_haiku_sub_agents():
    assert models.ORCHESTRATOR_DEFAULT == "claude-opus-5-5"
    assert models.role_models({}) == {r: "claude-haiku-5-5" for r in models.WORKER_ROLES}
    assert "orchestrator" not in models.WORKER_ROLES


def test_role_overrides_and_validation():
    env = {
        "PLATO_SCIENTIST_MODEL": "claude-sonnet-5-5",
        "PLATO_ROLE_MODELS": '{"skeptic": "claude-opus-5-5"}',
    }
    got = models.role_models(env)
    assert got["skeptic"] == "claude-opus-5-5"
    assert {m for r, m in got.items() if r != "skeptic"} == {"claude-sonnet-5-5"}
    for raw, msg in (
        ("{nope", "not valid JSON"),
        ('["skeptic"]', "JSON object"),
        ('{"orchestrator": "claude-haiku-5-5"}', "unknown roles"),
        ('{"skeptic": 5}', "model id"),
    ):
        with pytest.raises(models.ModelConfigError, match=msg):
            models.role_models({"PLATO_ROLE_MODELS": raw})


def test_weights_follow_price_and_unknown_models_are_never_undercharged():
    assert models.allowance_tokens("claude-haiku-5-5", 1000) == 1000
    assert models.allowance_tokens("claude-opus-5-5", 1000) == 40_000
    assert models.weight("claude-made-up-9") == max(models.WEIGHTS.values())
    assert models.allowance_tokens("claude-opus-5-5", -5) == 0


def test_every_model_call_purpose_has_a_role():
    """A new call purpose must be given a role, or it would silently run on the default."""
    src = "\n".join(p.read_text("utf-8") for p in (ROOT / "plato/scientist").rglob("*.py"))
    # Sandbox purposes label E2B/Modal sessions, not model calls.
    sandbox = {"workspace", "compile", "experiment"}
    purposes = set(re.findall(r'purpose="([a-z_]+)"', src)) - sandbox
    purposes |= {"workspace_engineer"} | {f"review_{a}" for a in ("methodology", "statistics", "novelty", "writing")}
    unmapped = sorted(p for p in purposes if models.role_for(p) is None)
    assert not unmapped, unmapped


def test_frozen_role_map():
    assert models.frozen_role_models({"workers": 2}) is None
    assert models.frozen_role_models({"models": {"skeptic": "claude-opus-5-5"}}) == {
        "skeptic": "claude-opus-5-5"
    }
    with pytest.raises(models.ModelConfigError):
        models.frozen_role_models({"models": ["x"]})


async def test_each_role_runs_on_its_model_and_is_charged_at_its_weight(store, campaign):
    _, cid = campaign
    parsed = FigureCritique(quality_score=0.7, issues=[])
    messages = _FakeMessages(_response(parsed=parsed))
    role_map = models.role_models({}) | {"skeptic": "claude-opus-5-5"}
    model = AnthropicScientistModel(
        store,
        models=role_map,
        client=SimpleNamespace(messages=messages),
        writing_reserve_tokens=0,
    )
    kw = dict(system="sys", prompt="p", schema=FigureCritique)
    await model.structured(campaign_id=cid, purpose="figure_critique", **kw)
    assert messages.kwargs["model"] == "claude-haiku-5-5"
    assert (await store.get_campaign(cid))["tokens_used"] == 160  # 100 + 50 + 10, weight 1
    await model.structured(campaign_id=cid, purpose="skeptic", **kw)
    assert messages.kwargs["model"] == "claude-opus-5-5"
    assert (await store.get_campaign(cid))["tokens_used"] == 160 + 160 * 40
    ledger = await store.pool.fetchval(
        "SELECT sum(tokens) FROM plato.usage_events WHERE campaign_id = $1", cid
    )
    assert ledger == 160 + 160 * 40


async def test_service_freezes_role_models_on_create(pg_dsn, monkeypatch):
    from plato.scientist.service import create_app

    monkeypatch.setenv("PLATO_ROLE_MODELS", '{"paper_writer": "claude-sonnet-5-5"}')
    app = create_app(dsn=pg_dsn, internal_token="t")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = (await client.get("/healthz")).json()
            assert health["models"]["paper_writer"] == "claude-sonnet-5-5"
            r = await client.post(
                "/internal/campaigns",
                json={"question": "Does y exceed 2?", "start": False},
                headers={"X-Plato-Internal-Token": "t"},
            )
            assert r.status_code == 202, r.text
            c = await app.state.store.get_campaign(uuid.UUID(r.json()["id"]))
            assert c["config"]["models"]["paper_writer"] == "claude-sonnet-5-5"
            assert c["config"]["models"]["skeptic"] == "claude-haiku-5-5"

    monkeypatch.setenv("PLATO_ROLE_MODELS", '{"nobody": "x"}')
    with pytest.raises(models.ModelConfigError):
        create_app(dsn=pg_dsn, internal_token="t")
