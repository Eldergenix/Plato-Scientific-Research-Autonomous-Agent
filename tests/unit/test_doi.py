"""Unit tests for :mod:`plato.retrieval.doi`."""
from __future__ import annotations

import pytest

from plato.retrieval.doi import (
    is_valid_arxiv_id,
    is_valid_doi,
    normalize_doi,
    parse_arxiv_id,
    parse_doi,
)


# ---------------------------------------------------------------------------
# DOI parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Bare DOI
        ("10.1038/s41586-021-03819-2", "10.1038/s41586-021-03819-2"),
        # https URL
        (
            "https://doi.org/10.1038/s41586-021-03819-2",
            "10.1038/s41586-021-03819-2",
        ),
        # http URL
        (
            "http://dx.doi.org/10.1038/s41586-021-03819-2",
            "10.1038/s41586-021-03819-2",
        ),
        # doi: prefix
        ("doi:10.1038/s41586-021-03819-2", "10.1038/s41586-021-03819-2"),
        # Mixed case is normalized to lowercase
        ("10.1038/S41586-021-03819-2", "10.1038/s41586-021-03819-2"),
        # Embedded in text
        (
            "see also 10.1234/abc.DEF for details",
            "10.1234/abc.def",
        ),
        # 9-digit registrant
        ("10.123456789/foo-bar", "10.123456789/foo-bar"),
        # Suffix with parentheses, semicolons, slashes
        ("10.1234/foo;bar(baz)/qux", "10.1234/foo;bar(baz)/qux"),
        # Trailing punctuation is stripped
        ("DOI: 10.1234/abc.", "10.1234/abc"),
        ("see 10.1234/abc, then proceed", "10.1234/abc"),
    ],
)
def test_parse_doi_valid(raw: str, expected: str) -> None:
    assert parse_doi(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not a doi at all",
        # 3-digit registrant is too short (regex requires 4-9)
        "10.123/foo",
        # Missing slash entirely
        "10.1234abc",
        # Just "10."
        "10.",
        None,
    ],
)
def test_parse_doi_invalid(raw: str | None) -> None:
    assert parse_doi(raw) is None


def test_normalize_doi_strips_whitespace_and_url() -> None:
    assert (
        normalize_doi("   https://doi.org/10.1234/ABC.def   ")
        == "10.1234/abc.def"
    )


def test_normalize_doi_none_passthrough() -> None:
    assert normalize_doi(None) is None
    assert normalize_doi("") is None


def test_is_valid_doi() -> None:
    assert is_valid_doi("10.1038/s41586-021-03819-2") is True
    assert is_valid_doi("https://doi.org/10.1038/s41586-021-03819-2") is True
    assert is_valid_doi("not a doi") is False
    assert is_valid_doi("") is False
    assert is_valid_doi(None) is False


# ---------------------------------------------------------------------------
# arXiv ID parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # New scheme — bare
        ("2401.12345", "2401.12345"),
        # New scheme — version suffix stripped
        ("2401.12345v1", "2401.12345"),
        ("2401.12345v23", "2401.12345"),
        # arXiv: prefix
        ("arXiv:2401.12345", "2401.12345"),
        ("arxiv:2401.12345v2", "2401.12345"),
        # https abs URL
        ("https://arxiv.org/abs/2401.12345", "2401.12345"),
        ("https://arxiv.org/abs/2401.12345v1", "2401.12345"),
        # 4-digit suffix is acceptable too (older 2007–2014 era)
        ("0704.0001", "0704.0001"),
        ("https://arxiv.org/abs/0704.0001v1", "0704.0001"),
        # Pre-2007 form
        ("cond-mat/0211143", "cond-mat/0211143"),
        ("cond-mat/0211143v2", "cond-mat/0211143"),
        ("arXiv:hep-th/9901001", "hep-th/9901001"),
        ("https://arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
        # Pre-2007 with subject class subdivision
        ("astro-ph.CO/0506000", "astro-ph.CO/0506000"),
    ],
)
def test_parse_arxiv_id_valid(raw: str, expected: str) -> None:
    assert parse_arxiv_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "no arxiv here",
        # 3-digit suffix too short
        "2401.123",
        # Too many digits in YYMM
        "12345.12345",
        None,
    ],
)
def test_parse_arxiv_id_invalid(raw: str | None) -> None:
    assert parse_arxiv_id(raw) is None


def test_is_valid_arxiv_id() -> None:
    assert is_valid_arxiv_id("2401.12345") is True
    assert is_valid_arxiv_id("arXiv:2401.12345v3") is True
    assert is_valid_arxiv_id("cond-mat/0211143") is True
    assert is_valid_arxiv_id("not an arxiv id") is False
    assert is_valid_arxiv_id("") is False
    assert is_valid_arxiv_id(None) is False
