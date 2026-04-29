"""Phase 1 — §5.9: DomainProfile registry behaves as expected."""
from __future__ import annotations

import pytest

from plato.domain import (
    DomainProfile,
    get_domain,
    list_domains,
    register_domain,
)


def test_astro_profile_registered_by_default():
    """The astro profile ships pre-registered with the expected defaults."""
    astro = get_domain("astro")
    assert astro.name == "astro"
    assert "ads" in astro.retrieval_sources
    assert "arxiv" in astro.retrieval_sources
    assert "AAS" in astro.journal_presets
    assert astro.executor == "cmbagent"


def test_list_domains_includes_astro():
    assert "astro" in list_domains()


def test_register_domain_adds_new_profile():
    profile = DomainProfile(
        name="biology-test",
        retrieval_sources=["pubmed", "openalex"],
        keyword_extractor="mesh",
        journal_presets=["NATURE", "CELL"],
        executor="modal",
        novelty_corpus="pubmed",
    )
    register_domain(profile)
    assert get_domain("biology-test").retrieval_sources == ["pubmed", "openalex"]
    assert "biology-test" in list_domains()


def test_register_domain_rejects_duplicate_without_overwrite():
    profile = DomainProfile(name="dup-test")
    register_domain(profile)
    with pytest.raises(ValueError, match="already registered"):
        register_domain(DomainProfile(name="dup-test"))


def test_register_domain_overwrites_when_asked():
    register_domain(DomainProfile(name="overwrite-test", executor="a"))
    register_domain(DomainProfile(name="overwrite-test", executor="b"), overwrite=True)
    assert get_domain("overwrite-test").executor == "b"


def test_get_domain_unknown_raises():
    with pytest.raises(KeyError, match="Unknown domain"):
        get_domain("does-not-exist")
