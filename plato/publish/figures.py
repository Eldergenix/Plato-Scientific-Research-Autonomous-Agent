"""Figures for the package: the experiments' own plots and one summary chart.

Experiment plots were written by model code inside the sandbox, so every image is
decoded and re-encoded with Pillow (which refuses decompression bombs) before TeX or
pandoc sees it. Figures are ranked by the vision critique's quality score; the
journal's display-item limit decides how many go in the main text, the rest go to the
Supplementary Information. The summary chart is drawn here from the authoritative
metrics in the graph, in PDF (vector, for LaTeX) and 300 dpi PNG (for Word and JATS),
with its source data written beside it.
"""

from __future__ import annotations

import io
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .collect import Materials

MAX_PIXELS = 40_000_000
SUMMARY_FILE = "fig_summary"


@dataclass
class Plot:
    finding_id: uuid.UUID | None
    node_id: uuid.UUID
    finding_title: str
    png: bytes
    quality: float | None


def _clean_png(data: bytes) -> bytes | None:
    """Re-encoded PNG, or None if the bytes are not a sane raster image."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > MAX_PIXELS or im.width < 16 or im.height < 16:
                return None
            im = (
                im.convert("RGBA")
                if im.mode in ("P", "LA", "RGBA")
                else im.convert("RGB")
            )
            if im.mode == "RGBA":  # TeX and Word render transparency inconsistently
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im, mask=im.split()[3])
                im = bg
            out = io.BytesIO()
            im.save(out, "PNG", optimize=True, dpi=(300, 300))
            return out.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError, SyntaxError):
        return None


def experiment_plots(m: Materials) -> list[Plot]:
    """Plots attached to the facts behind each finding, verified findings first, then by
    the vision critique's quality score. Plots of facts no finding cites come last."""
    nodes = {n["id"]: n for n in m.nodes}
    finding_of: dict[uuid.UUID, uuid.UUID] = {}
    order = sorted(
        (n for n in m.nodes if n["node_type"] == "finding"),
        key=lambda n: (n["status"] != "verified", -(float(n["confidence_score"] or 0))),
    )
    for f in order:
        for nid in m.lineage.get(f["id"], []):
            finding_of.setdefault(nid, f["id"])
    rank = {f["id"]: i for i, f in enumerate(order)}
    seen: set[str] = set()
    plots = []
    for e in m.evidence:
        if e.kind != "plot_png":
            continue
        png = _clean_png(e.content)
        if png is None:
            continue
        digest = str(hash(png))
        if digest in seen:  # replications often save the same picture
            continue
        seen.add(digest)
        fid = finding_of.get(e.node_id)
        title = (
            nodes[fid]["title"]
            if fid
            else (nodes.get(e.node_id) or {}).get("title", "")
        )
        plots.append(Plot(fid, e.node_id, title, png, e.quality))
    plots.sort(
        key=lambda p: (
            rank.get(p.finding_id, len(rank)) if p.finding_id else len(rank) + 1,
            -(p.quality if p.quality is not None else 0.5),
        )
    )
    return plots


def _primary(n: dict[str, Any]) -> tuple[str, float] | None:
    metrics = n.get("metrics") or {}
    key = metrics.get("primary_metric")
    value = metrics.get(key) if isinstance(key, str) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return key, float(value)


def summary_rows(m: Materials) -> list[dict[str, Any]]:
    """One row per finding with a numeric primary metric (the chart's source data)."""
    rows = []
    for n in m.nodes:
        if n["node_type"] != "finding" or n["status"] not in (
            "verified",
            "refuted",
            "inconclusive",
        ):
            continue
        p = _primary(n)
        if p is None:
            continue
        rows.append(
            {
                "finding": n["title"],
                "status": n["status"],
                "primary_metric": p[0],
                "value": p[1],
                "confidence": float(n["confidence_score"])
                if n["confidence_score"] is not None
                else None,
            }
        )
    rows.sort(key=lambda r: (r["status"] != "verified", -(r["confidence"] or 0)))
    return rows[:12]


def _short(text: str, n: int = 48) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def summary_chart(rows: list[dict[str, Any]], out_dir: Path) -> bool:
    """Skeptic confidence per finding, coloured by verification status, annotated with the
    measured primary metric. Writes ``fig_summary.pdf`` and ``fig_summary.png``."""
    if not rows:
        return False
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"verified": "#1f77b4", "inconclusive": "#9e9e9e", "refuted": "#d62728"}
    labels = [_short(r["finding"]) for r in rows][::-1]
    conf = [(r["confidence"] or 0.0) for r in rows][::-1]
    cols = [colors[r["status"]] for r in rows][::-1]
    notes = [f"{r['primary_metric']} = {r['value']:.4g}" for r in rows][::-1]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "pdf.fonttype": 42,  # embed TrueType: journals reject Type 3 fonts
            "svg.hashsalt": "plato",
        }
    )
    fig, ax = plt.subplots(figsize=(7.0, 0.42 * len(rows) + 1.1))
    bars = ax.barh(range(len(rows)), conf, color=cols, height=0.6)
    ax.set_yticks(range(len(rows)), labels)
    ax.set_xlim(0, 1.18)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("Skeptic confidence")
    for bar, note in zip(bars, notes):
        ax.text(
            bar.get_width() + 0.01,
            bar.get_y() + bar.get_height() / 2,
            note,
            va="center",
            fontsize=7,
        )
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=c)
        for s, c in colors.items()
        if any(r["status"] == s for r in rows)
    ]
    names = [s for s in colors if any(r["status"] == s for r in rows)]
    ax.legend(handles, names, loc="lower right", frameon=False, fontsize=7)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        out_dir / f"{SUMMARY_FILE}.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    fig.savefig(out_dir / f"{SUMMARY_FILE}.png", dpi=300, metadata={"Software": None})
    plt.close(fig)
    (out_dir / f"{SUMMARY_FILE}_source_data.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return True
