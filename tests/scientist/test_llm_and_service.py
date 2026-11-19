"""Request-shape tests for the Anthropic model adapter and the container HTTP service."""

from __future__ import annotations

import base64
import itertools
import uuid
from types import SimpleNamespace

import httpx
import pytest

from plato.scientist.db.store import BudgetExceeded
from plato.scientist.llm import AnthropicScientistModel, ModelOutputError, ModelRefusal
from plato.scientist.schemas import FigureCritique


class _FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def stream(self, **kwargs):
        self.kwargs = kwargs
        return _FakeStream(self.response)


class _FakeStream:
    def __init__(self, response):
        self.response = response
        self.text_stream = self._text()

    async def _text(self):
        for block in getattr(self.response, "content", []):
            text = getattr(block, "text", "")
            for i in range(0, len(text), 7):
                yield text[i : i + 7]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self.response


def _response(stop_reason="end_turn", parsed=None, in_tok=100, out_tok=50):
    usage = SimpleNamespace(
        input_tokens=in_tok,
        output_tokens=out_tok,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=10,
    )
    content = (
        [SimpleNamespace(type="text", text=parsed.model_dump_json())] if parsed else []
    )
    return SimpleNamespace(
        stop_reason=stop_reason, content=content, usage=usage, stop_details=None
    )


async def test_model_request_shape_and_budget_settlement(store, campaign):
    _, cid = campaign
    parsed = FigureCritique(quality_score=0.7, issues=[])
    messages = _FakeMessages(_response(parsed=parsed))
    model = AnthropicScientistModel(
        store, client=SimpleNamespace(messages=messages), writing_reserve_tokens=0
    )
    out = await model.structured(
        campaign_id=cid,
        purpose="figure_critique",
        system="sys",
        prompt="p",
        schema=FigureCritique,
        effort="low",
        images=[b"\x89PNG..."],
    )
    assert out == parsed
    kw = messages.kwargs
    assert kw["model"] == "claude-haiku-5-5"
    assert kw["output_config"]["effort"] == "low"
    fmt = kw["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert set(fmt["schema"]["properties"]) == {"quality_score", "issues"}
    assert "output_format" not in kw  # parsed by us after the stop_reason check
    assert (
        "temperature" not in kw and "thinking" not in kw
    )  # Haiku 5.5 rejects non-default sampling
    assert kw["messages"][0]["content"][0]["type"] == "image"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Reservation replaced by real usage: 100 + 50 + 0 + 10.
    assert (await store.get_campaign(cid))["tokens_used"] == 160


async def test_model_refusal_and_truncation_are_errors(store, campaign):
    _, cid = campaign
    for stop, exc in (("refusal", ModelRefusal), ("max_tokens", ModelOutputError)):
        model = AnthropicScientistModel(
            store, client=SimpleNamespace(messages=_FakeMessages(_response(stop)))
        )
        with pytest.raises(exc):
            await model.structured(
                campaign_id=cid,
                purpose="x",
                system="s",
                prompt="p",
                schema=FigureCritique,
            )


async def test_model_respects_writing_reserve(store, campaign):
    program, _ = campaign
    cid = await store.create_campaign(program, "small", token_budget_max=60_000)
    messages = _FakeMessages(
        _response(parsed=FigureCritique(quality_score=1, issues=[]))
    )
    model = AnthropicScientistModel(
        store, client=SimpleNamespace(messages=messages), writing_reserve_tokens=55_000
    )
    with pytest.raises(BudgetExceeded):
        await model.structured(
            campaign_id=cid,
            purpose="skeptic",
            system="s",
            prompt="p",
            schema=FigureCritique,
            max_tokens=8000,
        )
    assert messages.kwargs is None  # no request was sent
    await model.structured(
        campaign_id=cid,
        purpose="manuscript",
        system="s",
        prompt="p",
        schema=FigureCritique,
        max_tokens=8000,
    )


async def test_service_requires_internal_token_and_creates_campaigns(pg_dsn):
    from plato.scientist.service import create_app

    app = create_app(dsn=pg_dsn, internal_token="secret-token")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            assert (await client.get("/healthz")).json()["ok"] is True
            body = {
                "question": "Does y exceed 2?",
                "start": False,
                "datasets": [
                    {
                        "file_name": "train.csv",
                        "content_base64": base64.b64encode(b"x,y\n1,3\n").decode(),
                    }
                ],
            }
            assert (
                await client.post("/internal/campaigns", json=body)
            ).status_code == 401
            bad = await client.post(
                "/internal/campaigns",
                json=body,
                headers={"X-Plato-Internal-Token": "nope"},
            )
            assert bad.status_code == 401
            ok = await client.post(
                "/internal/campaigns",
                json=body,
                headers={"X-Plato-Internal-Token": "secret-token"},
            )
            assert ok.status_code == 202, ok.text
            cid = ok.json()["id"]
            summary = await client.get(
                f"/internal/campaigns/{cid}",
                headers={"X-Plato-Internal-Token": "secret-token"},
            )
            assert summary.json()["campaign"]["status"] == "ideation"
            # A Worker-chosen id routes the campaign and makes a retried create idempotent.
            fixed = "6f1c1c5e-8a52-4b7e-9d5e-2f3b9e0c1a11"
            hdr = {"X-Plato-Internal-Token": "secret-token"}
            for _ in range(2):
                again = await client.post(
                    f"/internal/campaigns?id={fixed}", json=body, headers=hdr
                )
                assert again.status_code == 202 and again.json()["id"] == fixed
            store = app.state.store
            assert (
                await store.pool.fetchval(
                    "SELECT count(*) FROM plato.research_campaigns WHERE id = $1::uuid",
                    fixed,
                )
                == 1
            )
            bad_ds = dict(
                body, datasets=[{"file_name": "../x", "content_base64": "eA=="}]
            )
            r = await client.post(
                "/internal/campaigns",
                json=bad_ds,
                headers={"X-Plato-Internal-Token": "secret-token"},
            )
            assert r.status_code == 422


async def test_service_records_owner_and_never_runs_own_key_campaigns_without_it(
    pg_dsn,
):
    """The Worker passes the owner, project and (for own-key campaigns) the owner's key;
    an own-key campaign is never created or resumed on the default key."""
    from plato.scientist.service import create_app

    app = create_app(dsn=pg_dsn, internal_token="t")
    hdr = {"X-Plato-Internal-Token": "t"}
    async with app.router.lifespan_context(app):
        store = app.state.store
        account = await store.pool.fetchval(
            "INSERT INTO plato.accounts (email, password_hash) VALUES ($1, $2) RETURNING id",
            f"{uuid.uuid4().hex}@example.org",
            "x" * 64,
        )
        project = await store.pool.fetchval(
            "INSERT INTO plato.projects (account_id, title) VALUES ($1, 'p') RETURNING id",
            account,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            body = {"question": "Does y exceed 2?", "start": False}
            q = f"account={account}&project={project}"
            refused = await client.post(
                f"/internal/campaigns?{q}&own_key=true", json=body, headers=hdr
            )
            assert refused.status_code == 422
            made = await client.post(
                f"/internal/campaigns?{q}&own_key=true",
                json=body,
                headers={**hdr, "X-Plato-Anthropic-Key": "sk-ant-test"},
            )
            assert made.status_code == 202, made.text
            cid = uuid.UUID(made.json()["id"])
            row = await store.get_campaign(cid)
            assert (row["account_id"], row["project_id"], row["own_key"]) == (
                account,
                project,
                True,
            )
            run = await client.post(f"/internal/campaigns/{cid}/run", headers=hdr)
            assert run.json() == {
                "id": str(cid),
                "started": False,
                "reason": "owner key missing",
            }
            assert not app.state.runner.tasks


async def test_truncated_or_invalid_output_is_output_error_and_settles_usage(
    store, campaign
):
    _, cid = campaign
    before = (await store.get_campaign(cid))["tokens_used"]
    bad = _response()
    bad.content = [SimpleNamespace(type="text", text='{"quality_score": 0.5, "iss')]
    for resp in (_response("max_tokens"), bad):
        model = AnthropicScientistModel(
            store, client=SimpleNamespace(messages=_FakeMessages(resp))
        )
        with pytest.raises(ModelOutputError):
            await model.structured(
                campaign_id=cid,
                purpose="x",
                system="s",
                prompt="p",
                schema=FigureCritique,
            )
    # Every request was billed (100 + 50 + 10 each) even though they failed: the
    # truncated call was sent twice (the retry with a larger cap was cut off too).
    assert (await store.get_campaign(cid))["tokens_used"] == before + 480


class _ScriptedMessages:
    """Answers each stream with the next scripted response; records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeStream(self.responses.pop(0))


async def test_plan_truncated_at_max_tokens_is_retried_with_a_larger_cap(
    store, campaign
):
    """Reproduces 'Halted. plan_intents: output truncated at max_tokens=8000': adaptive
    thinking plus the specs ran past the cap. The call now retries once with a larger cap
    instead of halting the campaign."""
    _, cid = campaign
    before = (await store.get_campaign(cid))["tokens_used"]
    parsed = FigureCritique(quality_score=0.9, issues=[])
    messages = _ScriptedMessages(_response("max_tokens"), _response(parsed=parsed))
    model = AnthropicScientistModel(
        store, client=SimpleNamespace(messages=messages), writing_reserve_tokens=0
    )
    out = await model.structured(
        campaign_id=cid,
        purpose="plan_intents",
        system="s",
        prompt="p",
        schema=FigureCritique,
        max_tokens=8000,
    )
    assert out == parsed
    assert [c["max_tokens"] for c in messages.calls] == [8000, 32000]
    # Both attempts are charged.
    assert (await store.get_campaign(cid))["tokens_used"] == before + 320


async def test_retry_never_exceeds_the_output_ceiling(store, campaign):
    _, cid = campaign
    messages = _ScriptedMessages(_response("max_tokens"), _response("max_tokens"))
    model = AnthropicScientistModel(
        store, client=SimpleNamespace(messages=messages), writing_reserve_tokens=0
    )
    with pytest.raises(ModelOutputError, match="max_tokens=64000"):
        await model.structured(
            campaign_id=cid,
            purpose="manuscript",
            system="s",
            prompt="p",
            schema=FigureCritique,
            max_tokens=48000,
        )
    assert [c["max_tokens"] for c in messages.calls] == [48000, 64000]


def test_planner_asks_for_room_to_think():
    from plato.scientist import nodes

    assert nodes.PLAN_MAX_TOKENS >= 16_000


async def test_on_text_receives_the_growing_output(store, campaign):
    _, cid = campaign
    parsed = FigureCritique(quality_score=0.7, issues=["a", "b"])
    seen: list[str] = []

    async def sink(text: str) -> None:
        seen.append(text)
        raise RuntimeError("display sink failures must not fail the call")

    model = AnthropicScientistModel(
        store,
        client=SimpleNamespace(messages=_FakeMessages(_response(parsed=parsed))),
        writing_reserve_tokens=0,
    )
    out = await model.structured(
        campaign_id=cid,
        purpose="manuscript",
        system="s",
        prompt="p",
        schema=FigureCritique,
        on_text=sink,
    )
    assert out == parsed
    assert len(seen) > 2 and seen[-1] == parsed.model_dump_json()
    assert all(b.startswith(a) for a, b in itertools.pairwise(seen))


async def test_monthly_cap_is_checked_atomically_on_create(pg_dsn):
    """A default-key campaign is admitted only if its whole budget fits in the account's
    remaining monthly allowance (unfinished campaigns hold their unspent budget, agent
    usage counts, own-key spend does not), and a retried create is never refused."""
    from plato.scientist.service import create_app

    app = create_app(dsn=pg_dsn, internal_token="t")
    hdr = {"X-Plato-Internal-Token": "t"}
    async with app.router.lifespan_context(app):
        store = app.state.store
        account = await store.pool.fetchval(
            "INSERT INTO plato.accounts (email, password_hash) VALUES ($1, $2) RETURNING id",
            f"{uuid.uuid4().hex}@example.org",
            "x" * 64,
        )
        await store.pool.execute(
            "INSERT INTO plato.agent_usage (account_id, tokens, own_key) VALUES ($1, 50000, false),"
            " ($1, 999999, true)",
            account,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            body = {
                "question": "Does y exceed 2?",
                "start": False,
                "token_budget": 200_000,
            }
            first = uuid.uuid4()
            q = f"account={account}&cap=500000"
            ok = await client.post(
                f"/internal/campaigns?id={first}&{q}", json=body, headers=hdr
            )
            assert ok.status_code == 202, ok.text
            assert (
                await store.pool.fetchval(
                    "SELECT plato.account_committed_tokens($1)", account
                )
                == 250_000
            )
            # 250k committed + 200k fits in 500k; a third 200k does not.
            assert (
                await client.post(f"/internal/campaigns?{q}", json=body, headers=hdr)
            ).status_code == 202
            over = await client.post(f"/internal/campaigns?{q}", json=body, headers=hdr)
            assert over.status_code == 402 and "left this month" in over.text
            # Retrying the first create (same id) is idempotent, not a new spend.
            again = await client.post(
                f"/internal/campaigns?id={first}&{q}", json=body, headers=hdr
            )
            assert again.status_code == 202
            # Own-key campaigns are not capped and a cap needs an account.
            own = await client.post(
                f"/internal/campaigns?account={account}&own_key=true",
                json=body,
                headers={**hdr, "X-Plato-Anthropic-Key": "sk-ant-test"},
            )
            assert own.status_code == 202
            assert (
                await client.post("/internal/campaigns?cap=1", json=body, headers=hdr)
            ).status_code == 422
            # A finished campaign only counts what it was charged this month.
            await store.pool.execute(
                "UPDATE plato.research_campaigns SET status = 'completed' WHERE id = $1",
                first,
            )
            assert (
                await store.pool.fetchval(
                    "SELECT plato.account_committed_tokens($1)", account
                )
                == 250_000
            )
