"""Phase 2 — R3: unit tests for :class:`plato.tools.citation_validator.CitationValidator`.

These tests do **no** real network I/O. We inject a mocked
:class:`httpx.AsyncClient` whose ``get``/``head`` methods are
:class:`unittest.mock.AsyncMock` instances; the mocks are dispatched per URL
so a single test can simulate Crossref, arXiv, and URL-liveness responses
simultaneously. ``respx`` is optional and not installed in the dev
environment, so we use plain ``AsyncMock`` instead.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from plato.state.models import Source
from plato.tools.citation_validator import CitationValidator


# ---------- fixtures & helpers --------------------------------------------


def _make_source(
    *,
    id: str = "src-1",
    doi: str | None = None,
    arxiv_id: str | None = None,
    url: str | None = None,
    pdf_url: str | None = None,
) -> Source:
    return Source(
        id=id,
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
        pdf_url=pdf_url,
        title="Some Paper",
        retrieved_via="crossref",
        fetched_at=datetime.now(timezone.utc),
    )


def _response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    """Build an :class:`httpx.Response` with the given status and JSON body."""
    if json_body is not None:
        return httpx.Response(status_code=status_code, json=json_body)
    return httpx.Response(status_code=status_code)


def _mock_client(
    *,
    get_router: dict[str, httpx.Response] | None = None,
    head_router: dict[str, httpx.Response] | None = None,
    get_side_effect=None,
    head_side_effect=None,
) -> AsyncMock:
    """Build an :class:`httpx.AsyncClient` mock that dispatches by URL prefix.

    Either pass per-URL routers (``{url_prefix: response}``) or a custom
    ``side_effect`` callable per HTTP verb. The first matching prefix wins.
    """

    client = AsyncMock(spec=httpx.AsyncClient)

    async def _route(routes: dict[str, httpx.Response] | None, url: str, *_, **__):
        if routes is None:
            raise AssertionError(f"unexpected request to {url}")
        for prefix, resp in routes.items():
            if url.startswith(prefix):
                return resp
        raise AssertionError(f"no mock route matched {url}")

    async def _route_get(url, *a, **k):
        return await _route(get_router, url)

    async def _route_head(url, *a, **k):
        return await _route(head_router, url)

    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    else:
        client.get = AsyncMock(side_effect=_route_get)

    if head_side_effect is not None:
        client.head = AsyncMock(side_effect=head_side_effect)
    else:
        client.head = AsyncMock(side_effect=_route_head)

    client.aclose = AsyncMock()
    return client


# ---------- DOI / Crossref ------------------------------------------------


@pytest.mark.asyncio
async def test_valid_doi_resolves_and_is_not_retracted():
    src = _make_source(doi="10.1000/valid")
    client = _mock_client(
        get_router={"https://api.crossref.org/works/": _response(200, {"message": {}})},
    )
    v = CitationValidator(http_client=client)
    result = await v.validate(src)
    assert result.doi_resolved is True
    assert result.retracted is False
    assert result.error is None


@pytest.mark.asyncio
async def test_hallucinated_doi_returns_404_unresolved():
    src = _make_source(doi="10.9999/hallucinated")
    client = _mock_client(
        get_router={"https://api.crossref.org/works/": _response(404)},
    )
    v = CitationValidator(http_client=client)
    result = await v.validate(src)
    assert result.doi_resolved is False
    assert result.retracted is False
    assert result.error is None  # 404 is not an "error", just an unresolved DOI.


@pytest.mark.asyncio
async def test_doi_in_retraction_db_marks_retracted():
    src = _make_source(doi="10.1000/retracted-X")
    client = _mock_client(
        # Crossref might still resolve the (now-retracted) DOI.
        get_router={"https://api.crossref.org/works/": _response(200, {"message": {}})},
    )
    v = CitationValidator(
        http_client=client,
        retraction_db={"10.1000/retracted-x"},  # normalized lower-case
    )
    result = await v.validate(src)
    assert result.doi_resolved is True
    assert result.retracted is True


@pytest.mark.asyncio
async def test_crossref_update_to_retraction_marks_retracted():
    src = _make_source(doi="10.1000/has-update-to")
    payload = {
        "message": {
            "DOI": "10.1000/has-update-to",
            "update-to": [
                {
                    "DOI": "10.1000/original",
                    "type": "journal-article",
                    "update-type": "retraction",
                    "label": "Retraction of",
                }
            ],
        }
    }
    client = _mock_client(
        get_router={"https://api.crossref.org/works/": _response(200, payload)},
    )
    v = CitationValidator(http_client=client)
    result = await v.validate(src)
    assert result.doi_resolved is True
    assert result.retracted is True


# ---------- arXiv ----------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_arxiv_id_resolves():
    src = _make_source(arxiv_id="2401.12345")
    client = _mock_client(
        head_router={"https://export.arxiv.org/abs/": _response(200)},
    )
    v = CitationValidator(http_client=client)
    result = await v.validate(src)
    assert result.arxiv_resolved is True
    assert result.error is None


# ---------- URL liveness ---------------------------------------------------


@pytest.mark.asyncio
async def test_dead_url_marked_not_alive():
    src = _make_source(url="https://example.invalid/dead")
    client = _mock_client(
        head_router={"https://example.invalid/": _response(404)},
    )
    v = CitationValidator(http_client=client)
    result = await v.validate(src)
    assert result.url_alive is False


@pytest.mark.asyncio
async def test_live_url_marked_alive():
    src = _make_source(url="https://example.com/alive")
    client = _mock_client(
        head_router={"https://example.com/": _response(301)},
    )
    v = CitationValidator(http_client=client)
    result = await v.validate(src)
    assert result.url_alive is True


@pytest.mark.asyncio
async def test_url_timeout_yields_none_alive_with_error():
    src = _make_source(url="https://slow.example/timeout")

    async def _raise_timeout(*_a, **_k):
        raise httpx.ReadTimeout("simulated timeout")

    client = _mock_client(head_side_effect=_raise_timeout)
    v = CitationValidator(http_client=client)
    result = await v.validate(src)
    assert result.url_alive is None
    assert result.error is not None and "timeout" in result.error.lower()


# ---------- batch concurrency ---------------------------------------------


@pytest.mark.asyncio
async def test_validate_batch_returns_one_result_per_source():
    sources = [
        _make_source(id=f"s-{i}", doi=f"10.1000/{i}", arxiv_id=None, url=None)
        for i in range(7)
    ]
    client = _mock_client(
        get_router={"https://api.crossref.org/works/": _response(200, {"message": {}})},
    )
    v = CitationValidator(http_client=client)
    results = await v.validate_batch(sources, concurrency=3)

    assert len(results) == len(sources)
    assert [r.source_id for r in results] == [s.id for s in sources]
    assert all(r.doi_resolved is True for r in results)


@pytest.mark.asyncio
async def test_validate_batch_concurrency_must_be_positive():
    v = CitationValidator(http_client=_mock_client())
    with pytest.raises(ValueError, match="concurrency"):
        await v.validate_batch([], concurrency=0)


# ---------- async context manager / lifecycle ------------------------------


@pytest.mark.asyncio
async def test_async_context_manager_closes_owned_client():
    """When the validator owns its httpx client, ``__aexit__`` closes it."""
    async with CitationValidator() as v:
        assert v._owns_client is True
        owned = v._http
    # The owned client should be closed after the context exits.
    assert owned.is_closed is True


@pytest.mark.asyncio
async def test_async_context_manager_does_not_close_injected_client():
    """An injected client is owned by the caller and must NOT be closed."""
    injected = _mock_client()
    async with CitationValidator(http_client=injected) as v:
        assert v._owns_client is False
    injected.aclose.assert_not_awaited()
