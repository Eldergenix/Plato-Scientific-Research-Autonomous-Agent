"""Phase 2 (R4) tests for the arXiv ``SourceAdapter``."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from plato.retrieval import ADAPTER_REGISTRY
from plato.retrieval.sources.arxiv import ArxivAdapter


# A small but realistic arXiv Atom response (two entries). Whitespace and
# multi-line summaries deliberately mirror the real feed so the parser is
# exercised against the same shape it will see in production.
ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <link href="http://arxiv.org/api/query?search_query=all:cosmology&amp;start=0&amp;max_results=2" rel="self" type="application/atom+xml"/>
  <title type="html">ArXiv Query: search_query=all:cosmology&amp;start=0&amp;max_results=2</title>
  <id>http://arxiv.org/api/abc123</id>
  <updated>2024-01-15T00:00:00-05:00</updated>
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">12345</opensearch:totalResults>
  <opensearch:startIndex xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">0</opensearch:startIndex>
  <opensearch:itemsPerPage xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <updated>2024-01-15T17:00:00Z</updated>
    <published>2024-01-15T17:00:00Z</published>
    <title>Probing Dark Matter
      with Galactic Rotation Curves</title>
    <summary>  We present a new probe of dark matter using rotation curves
      from 1000 nearby galaxies. The signal is consistent with a CDM
      profile.  </summary>
    <author>
      <name>Alice Smith</name>
    </author>
    <author>
      <name>Bob Jones</name>
    </author>
    <link href="http://arxiv.org/abs/2401.12345v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf"/>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="astro-ph.CO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="astro-ph.CO" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2310.99999v2</id>
    <updated>2023-10-31T12:00:00Z</updated>
    <published>2023-10-31T12:00:00Z</published>
    <title>Inflation Without a Field</title>
    <summary>An alternative inflationary mechanism is proposed.</summary>
    <author>
      <name>Carol Lee</name>
    </author>
    <link href="http://arxiv.org/abs/2310.99999v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2310.99999v2" rel="related" type="application/pdf"/>
    <category term="astro-ph.CO" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""


@pytest.fixture
def atom_xml() -> str:
    return ATOM_XML


def test_arxiv_adapter_name():
    assert ArxivAdapter.name == "arxiv"
    assert ArxivAdapter().name == "arxiv"


def test_arxiv_adapter_is_in_registry_after_import():
    # Importing plato.retrieval.sources.arxiv (above) must auto-register
    # the adapter via ``register_adapter(..., overwrite=True)``.
    assert "arxiv" in ADAPTER_REGISTRY
    assert isinstance(ADAPTER_REGISTRY["arxiv"], ArxivAdapter)


@pytest.mark.asyncio
async def test_arxiv_search_parses_two_entries(atom_xml: str):
    mock_response = Mock(text=atom_xml, raise_for_status=Mock())
    with patch("plato.retrieval.sources.arxiv.httpx.AsyncClient") as Client:
        Client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        # __aexit__ is auto-magically a no-op AsyncMock from MagicMock,
        # but we set it explicitly to keep the mock graph readable.
        Client.return_value.__aexit__ = AsyncMock(return_value=None)

        adapter = ArxivAdapter()
        sources = await adapter.search("cosmology", limit=2)

    assert len(sources) == 2

    first, second = sources

    assert first.title == "Probing Dark Matter with Galactic Rotation Curves"
    assert first.authors == ["Alice Smith", "Bob Jones"]
    assert first.year == 2024
    assert first.arxiv_id == "2401.12345"
    assert first.id == "arxiv:2401.12345"
    assert first.abstract is not None
    assert first.abstract.startswith("We present a new probe of dark matter")
    assert first.pdf_url == "http://arxiv.org/pdf/2401.12345v1"
    assert first.url == "http://arxiv.org/abs/2401.12345v1"
    assert first.retrieved_via == "arxiv"
    assert first.fetched_at is not None

    assert second.title == "Inflation Without a Field"
    assert second.authors == ["Carol Lee"]
    assert second.year == 2023
    assert second.arxiv_id == "2310.99999"
    assert second.id == "arxiv:2310.99999"
    assert second.pdf_url == "http://arxiv.org/pdf/2310.99999v2"


@pytest.mark.asyncio
async def test_arxiv_search_zero_limit_returns_empty():
    adapter = ArxivAdapter()
    # Should short-circuit before any HTTP call.
    with patch("plato.retrieval.sources.arxiv.httpx.AsyncClient") as Client:
        result = await adapter.search("cosmology", limit=0)
    assert result == []
    Client.assert_not_called()


@pytest.mark.asyncio
async def test_arxiv_search_handles_empty_feed():
    empty_feed = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )
    mock_response = Mock(text=empty_feed, raise_for_status=Mock())
    with patch("plato.retrieval.sources.arxiv.httpx.AsyncClient") as Client:
        Client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        Client.return_value.__aexit__ = AsyncMock(return_value=None)

        adapter = ArxivAdapter()
        sources = await adapter.search("nothing matches", limit=5)

    assert sources == []
