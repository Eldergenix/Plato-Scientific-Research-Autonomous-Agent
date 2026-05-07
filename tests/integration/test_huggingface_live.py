from __future__ import annotations

import os

import httpx
import pytest


def _hf_token() -> str | None:
    return (
        os.getenv("HUGGINGFACE_API_KEY")
        or os.getenv("HUGGINGFACE_HUB_TOKEN")
        or os.getenv("HF_TOKEN")
    )


@pytest.mark.live
async def test_huggingface_whoami_live() -> None:
    token = _hf_token()
    if not token:
        pytest.skip("set HUGGINGFACE_API_KEY, HUGGINGFACE_HUB_TOKEN, or HF_TOKEN")

    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    assert isinstance(body, dict)
    assert body.get("name")
    assert isinstance(body.get("orgs", []), list)


@pytest.mark.live
async def test_huggingface_router_chat_completions_live() -> None:
    token = _hf_token()
    if not token:
        pytest.skip("set HUGGINGFACE_API_KEY, HUGGINGFACE_HUB_TOKEN, or HF_TOKEN")

    model = os.getenv("PLATO_HUGGINGFACE_LIVE_MODEL")
    if not model:
        pytest.skip("set PLATO_HUGGINGFACE_LIVE_MODEL to run the paid router smoke")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with: ok"}],
                "max_tokens": 4,
            },
        )

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()
    choices = body.get("choices")
    assert isinstance(choices, list)
    assert choices
