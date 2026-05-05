"""Post-stage Quarkdown rendering orchestrator.

When the paper stage finishes successfully, render the four doctypes
(paged, slides, docs, plain) into ``<project>/paper/quarkdown/``.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .quarkdown import RenderResult, render_qd
from .transformer import (
    DocMeta,
    to_qd_docs,
    to_qd_paper,
    to_qd_plain,
    to_qd_slides,
    write_qd,
)

log = logging.getLogger(__name__)


async def render_all_artifacts(
    project_root: Path,
    paper_md: str,
    slides_md: str | None,
    meta: DocMeta,
) -> dict[str, RenderResult]:
    """Render paper / slides / docs / plain artifacts.

    Outputs land in ``<project_root>/paper/quarkdown/{paged,slides,docs,plain}/``.

    ``slides_md`` is the slide_outline agent's output. When ``None`` or
    empty the slides bucket is skipped — the slide_outline node only
    runs after the paper revision loop terminates, so a paper that
    failed before that node won't have anything to render here.
    """
    qroot = project_root / "paper" / "quarkdown"
    qroot.mkdir(parents=True, exist_ok=True)
    results: dict[str, RenderResult] = {}

    # Empty paper_md would make Quarkdown emit a stub HTML containing
    # only the header directives — surface this loudly and skip the
    # paper/plain/docs buckets so we don't ship vacuous artifacts. The
    # caller (run_manager._post_paper_render) inspects the empty results
    # dict and publishes a render.qd.skipped event for the UI.
    if not paper_md or not paper_md.strip():
        log.warning(
            "Skipping Quarkdown render: paper_md is empty/whitespace-only "
            "(project=%s)",
            project_root,
        )
        return results

    # Paper / paged book layout
    paged_dir = qroot / "paged"
    qd = write_qd(to_qd_paper(paper_md, meta), paged_dir / "paper.qd")
    results["paged"] = await _safe_render(qd, paged_dir, doctype="paged")

    # Plain (notes / one-pager)
    plain_dir = qroot / "plain"
    qd = write_qd(to_qd_plain(paper_md, meta), plain_dir / "paper.qd")
    results["plain"] = await _safe_render(qd, plain_dir, doctype="plain")

    # Docs (knowledge base / docs site)
    docs_dir = qroot / "docs"
    qd = write_qd(to_qd_docs(paper_md, meta), docs_dir / "paper.qd")
    results["docs"] = await _safe_render(qd, docs_dir, doctype="docs")

    # Slides (presentation-grade — only if the slide_outline agent ran).
    # Empty slides_md is the common case (slide_outline node skipped),
    # so log at INFO not WARNING; absence here is not an error.
    if slides_md and slides_md.strip():
        slides_dir = qroot / "slides"
        qd = write_qd(to_qd_slides(slides_md, meta), slides_dir / "slides.qd")
        results["slides"] = await _safe_render(qd, slides_dir, doctype="slides")
    else:
        log.info(
            "Skipping Quarkdown slides render: slides_md is empty "
            "(project=%s)",
            project_root,
        )

    return results


async def _safe_render(qd: Path, out_dir: Path, *, doctype: str) -> RenderResult:
    """Run ``render_qd`` and convert any exception into a soft RenderResult.

    The orchestrator must never bubble up — a missing Quarkdown binary
    or a single doctype failure shouldn't abort the other three. The
    caller publishes one ``render.qd.completed`` event with whatever
    paths landed; downstream consumers inspect ``returncode`` to
    distinguish success from failure.
    """
    started = time.perf_counter()
    try:
        return await render_qd(qd, out_dir, pdf=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("Quarkdown render failed for %s: %s", doctype, exc)
        return RenderResult(
            html_path=None,
            pdf_path=None,
            stdout="",
            stderr=str(exc),
            returncode=-1,
        )
    finally:
        # Observe duration for both success and soft-fail; the doctype
        # label captures which artifact slot the time was spent on.
        try:
            from ..observability.metrics import RENDER_DURATION_SECONDS
            RENDER_DURATION_SECONDS.labels(doctype=doctype).observe(
                time.perf_counter() - started
            )
        except Exception:  # noqa: BLE001
            pass


__all__ = ["render_all_artifacts"]
