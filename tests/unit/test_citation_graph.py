"""Phase 5 / Workflow #7 — tests for the OpenAlex citation-graph expansion."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval.citation_graph import (
    expand_citations,
    expand_via_doi,
)
from plato.retrieval.orchestrator import retrieve_with_expansion
from plato.state.models import Source


def _seed(
    *,
    openalex_id: str | None = "W1",
    doi: str | None = None,
    title: str = "Seed Paper",
) -> Source:
    return Source(
        id=f"openalex:{openalex_id}" if openalex_id else f"local:{title}",
        openalex_id=openalex_id,
        doi=doi,
        title=title,
        retrieved_via="openalex",
        fetched_at=datetime.now(timezone.utc),
    )


def _work_payload(
    *, work_id: str, title: str = "Some Paper", doi: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"https://openalex.org/{work_id}",
        "title": title,
        "publication_year": 2023,
    }
    if doi is not None:
        payload["doi"] = f"https://doi.org/{doi}"
    return payload


def _response(payload: dict[str, Any], url: str = "https://api.openalex.org/works") -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", url))


def _make_get_mock(url_to_payload: dict[str, dict[str, Any]]) -> AsyncMock:
    """Return an AsyncMock whose response depends on the requested URL.

    Matches by *substring* so callers can express the intent ("URL contains
    /W1") without pinning the exact querystring shape.
    """

    async def _fake_get(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        for needle, payload in url_to_payload.items():
            if needle in url:
                return _response(payload, url=url)
        raise AssertionError(f"Unexpected URL in mocked client: {url}")

    return AsyncMock(side_effect=_fake_get)


@pytest.mark.asyncio
async def test_expand_citations_referenced_works_happy_path() -> None:
    seed = _seed(openalex_id="W1")
    routes = {
        # Seed lookup returns its bibliography list.
        "/works/W1": {
            "id": "https://openalex.org/W1",
            "title": "Seed",
            "referenced_works": [
                "https://openalex.org/W100",
                "https://openalex.org/W101",
            ],
        },
        # Batch resolve of those reference IDs.
        "filter=openalex": {
            "results": [
                _work_payload(work_id="W100", title="Ref One"),
                _work_payload(work_id="W101", title="Ref Two"),
            ]
        },
    }

    with patch("httpx.AsyncClient.get", new=_make_get_mock(routes)):
        out = await expand_citations([seed], direction="referenced_works")

    assert {s.openalex_id for s in out} == {"W100", "W101"}
    assert {s.title for s in out} == {"Ref One", "Ref Two"}
    assert all(s.retrieved_via == "openalex" for s in out)


@pytest.mark.asyncio
async def test_expand_citations_skips_seeds_without_openalex_id() -> None:
    seeds = [
        _seed(openalex_id=None, title="No id A"),
        _seed(openalex_id=None, title="No id B"),
    ]

    # Even if the network were called, we'd raise — but we expect no calls.
    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=AssertionError("should not be called")),
    ):
        out = await expand_citations(seeds, direction="referenced_works")

    assert out == []


@pytest.mark.asyncio
async def test_expand_citations_cited_by_uses_cites_filter() -> None:
    seed = _seed(openalex_id="W42")
    captured: list[str] = []

    async def _fake_get(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        captured.append(url)
        return _response(
            {"results": [_work_payload(work_id="W500", title="Citing Paper")]},
            url=url,
        )

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=_fake_get)):
        out = await expand_citations([seed], direction="cited_by")

    assert len(captured) == 1
    assert "filter=cites:W42" in captured[0]
    assert {s.openalex_id for s in out} == {"W500"}


@pytest.mark.asyncio
async def test_expand_citations_depth_above_one_raises() -> None:
    with pytest.raises(NotImplementedError):
        await expand_citations([_seed()], depth=2)


@pytest.mark.asyncio
async def test_expand_citations_filters_self_loop() -> None:
    """A seed whose bibliography points back to itself must be filtered out."""
    seed = _seed(openalex_id="W1", title="Self-citing")
    routes = {
        "/works/W1": {
            "id": "https://openalex.org/W1",
            "title": "Self-citing",
            # Reference list includes the seed itself plus a real reference.
            "referenced_works": [
                "https://openalex.org/W1",
                "https://openalex.org/W200",
            ],
        },
        "filter=openalex": {
            "results": [
                _work_payload(work_id="W1", title="Self-citing"),
                _work_payload(work_id="W200", title="Real Reference"),
            ]
        },
    }

    with patch("httpx.AsyncClient.get", new=_make_get_mock(routes)):
        out = await expand_citations([seed], direction="referenced_works")

    assert {s.openalex_id for s in out} == {"W200"}


@pytest.mark.asyncio
async def test_expand_citations_dedup_across_seeds() -> None:
    """Two seeds sharing a referenced work should yield only one copy."""
    seed_a = _seed(openalex_id="WA", title="Seed A")
    seed_b = _seed(openalex_id="WB", title="Seed B")

    async def _fake_get(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "/works/WA" in url:
            return _response(
                {
                    "id": "https://openalex.org/WA",
                    "title": "Seed A",
                    "referenced_works": ["https://openalex.org/WSHARED"],
                },
                url=url,
            )
        if "/works/WB" in url:
            return _response(
                {
                    "id": "https://openalex.org/WB",
                    "title": "Seed B",
                    "referenced_works": ["https://openalex.org/WSHARED"],
                },
                url=url,
            )
        if "filter=openalex" in url:
            return _response(
                {
                    "results": [
                        _work_payload(work_id="WSHARED", title="Shared Ref"),
                    ]
                },
                url=url,
            )
        raise AssertionError(f"Unexpected URL: {url}")

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=_fake_get)):
        out = await expand_citations(
            [seed_a, seed_b], direction="referenced_works"
        )

    assert {s.openalex_id for s in out} == {"WSHARED"}
    assert len(out) == 1


@pytest.mark.asyncio
async def test_expand_via_doi_resolves_then_expands() -> None:
    routes = {
        # /works/doi:... → seed work record.
        "/works/doi": {
            "id": "https://openalex.org/W1",
            "title": "Resolved Seed",
            "doi": "https://doi.org/10.1234/abcd",
        },
        # Seed expansion: bibliography lookup.
        "/works/W1": {
            "id": "https://openalex.org/W1",
            "title": "Resolved Seed",
            "referenced_works": ["https://openalex.org/W777"],
        },
        # Batch resolve of references.
        "filter=openalex": {
            "results": [_work_payload(work_id="W777", title="Cited Paper")]
        },
    }

    with patch("httpx.AsyncClient.get", new=_make_get_mock(routes)):
        out = await expand_via_doi(["10.1234/abcd"])

    assert {s.openalex_id for s in out} == {"W777"}


@pytest.mark.asyncio
async def test_expand_via_doi_handles_unresolvable_doi() -> None:
    """A DOI that doesn't resolve should not poison the rest of the batch."""

    async def _fake_get(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "doi:bogus" in url:
            return httpx.Response(
                404, request=httpx.Request("GET", url), text="not found"
            )
        if "doi:10.1234%2Fgood" in url or "doi:10.1234/good" in url:
            return _response(
                {
                    "id": "https://openalex.org/W1",
                    "title": "Good seed",
                    "doi": "https://doi.org/10.1234/good",
                },
                url=url,
            )
        if "/works/W1" in url:
            return _response(
                {
                    "id": "https://openalex.org/W1",
                    "title": "Good seed",
                    "referenced_works": ["https://openalex.org/W2"],
                },
                url=url,
            )
        if "filter=openalex" in url:
            return _response(
                {"results": [_work_payload(work_id="W2", title="Ref Two")]},
                url=url,
            )
        raise AssertionError(f"Unexpected URL: {url}")

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=_fake_get)):
        out = await expand_via_doi(["bogus", "10.1234/good"])

    assert {s.openalex_id for s in out} == {"W2"}


# ---------------------------------------------------------------------------
# Orchestrator wiring: retrieve_with_expansion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_with_expansion_disabled_is_passthrough() -> None:
    """expand=False must NOT call expand_citations; it's a thin retrieve wrapper."""
    seeds = [_seed(openalex_id="W1")]

    with (
        patch(
            "plato.retrieval.orchestrator.retrieve",
            new=AsyncMock(return_value=seeds),
        ) as mock_retrieve,
        patch(
            "plato.retrieval.orchestrator.expand_citations",
            new=AsyncMock(return_value=[]),
        ) as mock_expand,
    ):
        out = await retrieve_with_expansion("q", limit=5, expand=False)

    assert out == seeds
    mock_retrieve.assert_awaited_once()
    mock_expand.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_with_expansion_enabled_calls_both() -> None:
    seeds = [_seed(openalex_id="W1", title="Seed")]
    expanded = [
        Source(
            id="openalex:W2",
            openalex_id="W2",
            title="Reference",
            retrieved_via="openalex",
            fetched_at=datetime.now(timezone.utc),
        )
    ]

    with (
        patch(
            "plato.retrieval.orchestrator.retrieve",
            new=AsyncMock(return_value=seeds),
        ) as mock_retrieve,
        patch(
            "plato.retrieval.orchestrator.expand_citations",
            new=AsyncMock(return_value=expanded),
        ) as mock_expand,
    ):
        out = await retrieve_with_expansion(
            "q", limit=5, expand=True, expansion_direction="cited_by"
        )

    mock_retrieve.assert_awaited_once()
    mock_expand.assert_awaited_once()
    # Direction propagated through.
    _, kwargs = mock_expand.call_args
    assert kwargs.get("direction") == "cited_by"

    assert {s.openalex_id for s in out} == {"W1", "W2"}
