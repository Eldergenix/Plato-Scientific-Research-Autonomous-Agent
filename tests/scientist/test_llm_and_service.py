"""Request-shape tests for the Anthropic model adapter and the container HTTP service."""

from __future__ import annotations

import base64
import itertools
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
    # Both calls were billed (100 + 50 + 10 each) even though they failed.
    assert (await store.get_campaign(cid))["tokens_used"] == before + 320


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
