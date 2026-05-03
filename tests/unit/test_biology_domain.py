"""Phase 2/5 — biology DomainProfile is registered alongside astro."""
from __future__ import annotations

from plato.domain import get_domain, list_domains


def test_biology_profile_registered() -> None:
    biology = get_domain("biology")
    assert biology.name == "biology"
    assert biology.retrieval_sources == ["pubmed", "openalex", "semantic_scholar"]
    assert biology.keyword_extractor == "mesh"
    assert biology.novelty_corpus == "pubmed"


def test_biology_journal_presets() -> None:
    biology = get_domain("biology")
    # The full list per the §5.5 spec, in order.
    assert biology.journal_presets == [
        "NATURE",
        "CELL",
        "SCIENCE",
        "PLOS_BIO",
        "ELIFE",
        "NONE",
    ]


def test_biology_appears_in_list_domains() -> None:
    domains = list_domains()
    assert "biology" in domains
    # Astro must still be there too — registration is additive.
    assert "astro" in domains


def test_biology_executor_is_local_jupyter() -> None:
    # Iter-21: biology now defaults to ``local_jupyter`` — a domain-neutral
    # executor that runs arbitrary Python without dragging in astro-specific
    # tooling. Users who want a sandboxed alternative can pass
    # ``executor="modal"`` / ``executor="e2b"`` per-call to
    # ``Plato.get_results`` or override the profile entirely.
    assert get_domain("biology").executor == "local_jupyter"
