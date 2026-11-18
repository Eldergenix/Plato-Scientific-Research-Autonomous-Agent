"""Live checks of the library tools against the real services (opt-in: ``pytest -m live``).

Every literature source is searched for real, and the citation checks run against
Crossref, doi.org and arXiv with known retracted, DataCite and invalid identifiers.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest

from plato import retrieval
from plato.scientist.citations import check_sources, exclusion_reason
from plato.scientist.nodes import default_retriever
from plato.scientist.profiles import get_profile
from plato.state.models import Source

pytestmark = [
    pytest.mark.live,
    # CI runs tests/scientist whole; real third-party calls only when asked for.
    pytest.mark.skipif(not os.environ.get("PLATO_LIVE"), reason="set PLATO_LIVE=1"),
]

QUERIES = {
    "arxiv": "bootstrap confidence interval coverage",
    "openalex": "bootstrap confidence interval coverage",
    "semantic_scholar": "bootstrap confidence interval coverage",
    "crossref": "bootstrap confidence interval coverage",
    "doaj": "false discovery rate",
    "europe_pmc": "differential gene expression false discovery rate",
    "pubmed": "differential gene expression false discovery rate",
    "datacite": "gene expression dataset",
    "ads": "exoplanet transit photometry",
    # OpenCitations Meta resolves DOIs; it is not a free-text search.
    "opencitations": "10.1038/nature12373",
}


@pytest.mark.parametrize("name", sorted(QUERIES))
async def test_every_source_returns_real_records(name):
    if name == "ads" and not (
        os.environ.get("ADS_API_KEY") or os.environ.get("ADS_DEV_KEY")
    ):
        pytest.skip("ADS needs ADS_API_KEY")
    results = await retrieval.get_adapter(name).search(QUERIES[name], 5)
    assert results, f"{name} returned nothing"
    assert all(r.title for r in results)


@pytest.mark.parametrize("profile", ["general", "biology", "astro"])
async def test_profile_retriever_ranks_across_sources(profile):
    query = {
        "general": "bootstrap confidence interval coverage small samples",
        "biology": "Benjamini-Hochberg false discovery rate gene expression",
        "astro": "exoplanet transit light curve detection",
    }[profile]
    sources = list(get_profile(profile).retrieval_sources)
    papers = await default_retriever(query, 8, sources=sources)
    assert len(papers) >= 4
    via = {p.retrieved_via for p in papers}
    if profile == "biology":
        assert via & {"pubmed", "europe_pmc"}, via


def _src(**kw) -> Source:
    return Source(
        id=uuid.uuid4().hex,
        retrieved_via="crossref",
        fetched_at=datetime.now(UTC),
        **kw,
    )


async def test_citation_checks_against_real_registries():
    datacite = await retrieval.get_adapter("datacite").search(
        "gene expression dataset", 5
    )
    datacite_doi = next(s.doi for s in datacite if s.doi)
    sources = [
        # Wakefield et al., Lancet 1998: retracted in 2010.
        _src(
            doi="10.1016/S0140-6736(97)11096-0",
            title="Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and pervasive developmental disorder in children",
            year=1998,
        ),
        # Obokata et al., Nature 2014 (STAP cells): retracted in 2014.
        _src(
            doi="10.1038/nature12968",
            title="Stimulus-triggered fate conversion of somatic cells into pluripotency",
            year=2014,
        ),
        _src(
            doi=datacite_doi,
            title=next(s.title for s in datacite if s.doi == datacite_doi),
        ),
        _src(arxiv_id="1706.03762", title="Attention Is All You Need", year=2017),
        _src(
            doi="10.9999/plato-not-a-real-doi-7f3c", title="A paper that does not exist"
        ),
    ]
    checks = await check_sources(sources)
    for src, check in zip(sources, checks, strict=True):
        print(src.doi or src.arxiv_id, check)
    assert exclusion_reason(checks[0]) == "retracted"
    assert exclusion_reason(checks[1]) == "retracted"
    assert checks[2]["doi_resolved"] is True  # DataCite DOI through doi.org
    assert checks[3]["arxiv_resolved"] is True and not checks[3]["retracted"]
    assert checks[4]["doi_resolved"] is False
