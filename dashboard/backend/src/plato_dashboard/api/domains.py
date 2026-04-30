"""Public read-only listing of registered ``DomainProfile``s.

Plato ships an ``astro`` profile by default (and ``biology`` as the second
built-in). The frontend's settings page calls ``GET /api/v1/domains`` to
populate the profile selector, so the response shape mirrors the fields
on ``plato.domain.DomainProfile`` exactly.

This route is deliberately tenant-agnostic: it serves configuration
metadata, not user data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from plato.domain import get_domain, list_domains

router = APIRouter()

# The default domain is currently hard-coded to astro: it's the only
# profile that has full Phase-2 retrieval wiring. When the user-preferences
# layer lands, the frontend overrides this default per-user.
DEFAULT_DOMAIN = "astro"


def _serialize(name: str) -> dict[str, Any]:
    profile = get_domain(name)
    return {
        "name": profile.name,
        "retrieval_sources": list(profile.retrieval_sources),
        "keyword_extractor": profile.keyword_extractor,
        "journal_presets": list(profile.journal_presets),
        "executor": profile.executor,
        "novelty_corpus": profile.novelty_corpus,
    }


@router.get("/api/v1/domains")
def get_domains() -> dict[str, Any]:
    """Return every registered domain profile + the global default."""
    return {
        "domains": [_serialize(name) for name in list_domains()],
        "default": DEFAULT_DOMAIN,
    }
