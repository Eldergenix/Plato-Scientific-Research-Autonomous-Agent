"""Supporting files: the data, code, logs and provenance behind every reported number.

Everything is written from the graph's immutable records (nodes, evidence receipts,
dataset blobs), never from model prose. Spreadsheets are written with fixed document
properties so the same campaign always produces byte-identical files.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from plato.scientist.nodes import code_from_patch

from .collect import Materials
from .figures import summary_rows

FIXED_TIME = datetime(
    2023, 11, 14, 22, 13, 20
)  # SOURCE_DATE_EPOCH 1700000000, naive for openpyxl
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str, fallback: str = "file") -> str:
    """A file name that is safe inside a zip and on every OS (no paths, no dot files)."""
    base = _SAFE.sub("_", name.replace("\\", "/").split("/")[-1]).strip("._")
    return (base or fallback)[:120]


def _jsonable(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.astimezone(UTC).isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None
    if hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
        return float(v)
    return v


def dumps(obj: Any) -> str:
    return (
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=_jsonable)
        + "\n"
    )


def _cell(v: Any) -> Any:
    """Excel-safe value: numbers stay numbers; text that a spreadsheet would execute as a
    formula (=, +, -, @) is prefixed with an apostrophe (CSV/formula injection)."""
    v = _jsonable(v)
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, (dict, list)):
        v = json.dumps(v, sort_keys=True, ensure_ascii=False)
    s = str(v)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not re.fullmatch(
        r"-?\d+(\.\d+)?([eE][-+]?\d+)?", s
    ):
        s = "'" + s
    return s[:32_000]  # Excel's cell limit is 32,767 characters


def _metric_keys(nodes: list[dict[str, Any]]) -> list[str]:
    keys: dict[str, None] = {}
    for n in nodes:
        for k, v in (n.get("metrics") or {}).items():
            if isinstance(v, (int, float, str, bool)) or v is None:
                keys.setdefault(k, None)
    return sorted(keys)


def tables(m: Materials) -> dict[str, tuple[list[str], list[list[Any]]]]:
    """Sheet name -> (header, rows). The same tables are written as CSV and as one
    multi-sheet workbook (Science asks for exactly that as Data S1)."""
    findings = [n for n in m.nodes if n["node_type"] == "finding"]
    facts = [n for n in m.nodes if n["node_type"] == "fact"]
    out: dict[str, tuple[list[str], list[list[Any]]]] = {}

    fkeys = _metric_keys(findings)
    out["findings"] = (
        ["id", "title", "status", "confidence", "statement", *fkeys],
        [
            [
                str(n["id"]),
                n["title"],
                n["status"],
                n["confidence_score"],
                n["hypothesis_or_spec"],
            ]
            + [(n.get("metrics") or {}).get(k) for k in fkeys]
            for n in findings
        ],
    )
    xkeys = _metric_keys(facts)
    out["experiments"] = (
        ["id", "title", "status", "observation", *xkeys],
        [
            [str(n["id"]), n["title"], n["status"], n["hypothesis_or_spec"]]
            + [(n.get("metrics") or {}).get(k) for k in xkeys]
            for n in facts
        ],
    )
    rows = summary_rows(m)
    out["figure_summary"] = (
        ["finding", "status", "primary_metric", "value", "confidence"],
        [
            [
                r["finding"],
                r["status"],
                r["primary_metric"],
                r["value"],
                r["confidence"],
            ]
            for r in rows
        ],
    )
    out["nodes"] = (
        [
            "id",
            "type",
            "status",
            "title",
            "priority",
            "confidence",
            "attempts",
            "created_at",
        ],
        [
            [
                str(n["id"]),
                n["node_type"],
                n["status"],
                n["title"],
                n["priority"],
                n["confidence_score"],
                n["attempt_count"],
                n["created_at"],
            ]
            for n in m.nodes
        ],
    )
    out["references"] = (
        ["key", "title", "authors", "year", "doi", "arxiv_id", "venue", "url"],
        [
            [
                k,
                (p.get("metadata") or {}).get("title") or p.get("canonical_name"),
                "; ".join(
                    a
                    for a in (p.get("metadata") or {}).get("authors") or []
                    if isinstance(a, str)
                ),
                (p.get("metadata") or {}).get("year"),
                (p.get("metadata") or {}).get("doi"),
                (p.get("metadata") or {}).get("arxiv_id"),
                (p.get("metadata") or {}).get("venue"),
                p.get("uri_or_commit"),
            ]
            for k, p in m.papers.items()
        ],
    )
    out["input_datasets"] = (
        ["name", "file", "bytes", "sha256", "scope"],
        [
            [
                d["canonical_name"],
                (d.get("metadata") or {}).get("file_name") or d["canonical_name"],
                len(d["content"]) if d.get("content") is not None else None,
                hashlib.sha256(d["content"]).hexdigest()
                if d.get("content") is not None
                else None,
                d.get("access_mode"),
            ]
            for d in m.datasets
        ],
    )
    return out


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if c is None else _cell(c) for c in r])
    # UTF-8 with BOM so Excel opens non-ASCII text correctly.
    path.write_text("﻿" + buf.getvalue(), encoding="utf-8")


def write_xlsx(
    path: Path, sheets: dict[str, tuple[list[str], list[list[Any]]]], readme: list[str]
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    for line in readme:
        ws.append([line])
    ws.column_dimensions["A"].width = 110
    bold = Font(bold=True)
    for name, (header, rows) in sheets.items():
        ws = wb.create_sheet(name[:31])
        ws.append(header)
        for c in ws[1]:
            c.font = bold
        for r in rows:
            ws.append([_cell(c) for c in r])
        ws.freeze_panes = "A2"
        for i, h in enumerate(header, 1):
            width = max(
                [len(str(h))]
                + [
                    len(str(r[i - 1] if r[i - 1] is not None else ""))
                    for r in rows[:200]
                ]
            )
            ws.column_dimensions[get_column_letter(i)].width = max(
                10, min(width + 2, 62)
            )
    wb.properties.creator = "Plato"
    wb.properties.created = FIXED_TIME
    wb.properties.modified = FIXED_TIME
    wb.properties.lastModifiedBy = "Plato"
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(_fixed_xlsx(buf.getvalue()))


def _fixed_xlsx(data: bytes) -> bytes:
    """openpyxl stamps the save time into docProps/core.xml; pin it (and the zip entry
    times) so the same campaign always gives the same workbook bytes."""
    from .convert import _rezip

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    stamp = FIXED_TIME.strftime("%Y-%m-%dT%H:%M:%SZ")
    files["docProps/core.xml"] = re.sub(
        rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
        rb"\g<1>" + stamp.encode() + rb"\g<2>",
        files["docProps/core.xml"],
    )
    return _rezip(files)


def write_data(m: Materials, root: Path) -> list[str]:
    """data/, code/, logs/, review/ under ``root``. Returns the written relative paths."""
    written: list[str] = []
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    sheets = tables(m)
    for name, (header, rows) in sheets.items():
        write_csv(data / f"{name}.csv", header, rows)
        written.append(f"data/{name}.csv")
    write_xlsx(
        data / "data_S1.xlsx",
        sheets,
        [
            "Data S1. Source data for this manuscript, one sheet per table.",
            "findings: every finding with its verification status, skeptic confidence and metrics.",
            "experiments: every executed experiment (fact) with its measured metrics.",
            "figure_summary: source data of the summary figure.",
            "nodes: the full exploration graph.",
            "references: the literature the campaign read.",
            "input_datasets: the input files with SHA-256 checksums (files in data/input/).",
            "All numbers were written by the experiment code, not by the language model.",
        ],
    )
    written.append("data/data_S1.xlsx")
    metrics = {
        str(n["id"]): {
            "type": n["node_type"],
            "title": n["title"],
            "status": n["status"],
            "metrics": n.get("metrics"),
        }
        for n in m.nodes
        if n["node_type"] in ("fact", "finding")
    }
    (data / "metrics.json").write_text(dumps(metrics), encoding="utf-8")
    written.append("data/metrics.json")
    sealed = [
        {
            "finding_id": str(e.node_id),
            **json.loads(e.content.decode("utf-8", "replace")),
        }
        for e in m.evidence
        if e.kind == "sealed_eval_json" and _is_json(e.content)
    ]
    if sealed:
        (data / "sealed_evaluation.json").write_text(dumps(sealed), encoding="utf-8")
        written.append("data/sealed_evaluation.json")
    inputs = [d for d in m.datasets if d.get("content") is not None]
    if inputs:
        (data / "input").mkdir(exist_ok=True)
        used: set[str] = set()
        for d in inputs:
            name = safe_name(
                (d.get("metadata") or {}).get("file_name") or d["canonical_name"],
                "dataset",
            )
            while name in used:
                name = "_" + name
            used.add(name)
            (data / "input" / name).write_bytes(d["content"])
            written.append(f"data/input/{name}")

    titles = {n["id"]: n["title"] for n in m.nodes}
    code, logs = root / "code", root / "logs"
    n_code = n_log = 0
    for e in m.evidence:
        stem = f"{safe_name(titles.get(e.node_id, 'experiment'))[:60]}_{str(e.node_id)[:8]}"
        if e.kind == "git_patch":
            code.mkdir(exist_ok=True)
            src = code_from_patch(e.content.decode("utf-8", "replace"))
            path = code / f"{stem}.py"
            if path.exists():
                path = code / f"{stem}_{str(e.id)[:6]}.py"
            path.write_text(
                f"# Experiment: {titles.get(e.node_id, '')}\n# Node: {e.node_id}\n{src}\n",
                encoding="utf-8",
            )
            written.append(f"code/{path.name}")
            n_code += 1
        elif e.kind == "stdout_log":
            logs.mkdir(exist_ok=True)
            path = logs / f"{stem}.log"
            if path.exists():
                path = logs / f"{stem}_{str(e.id)[:6]}.log"
            path.write_bytes(e.content)
            written.append(f"logs/{path.name}")
            n_log += 1
    review = root / "review"
    critiques = [
        {"node_id": str(e.node_id), "critique": e.content.decode("utf-8", "replace")}
        for e in m.evidence
        if e.kind == "vlm_critique"
    ]
    if m.review or critiques:
        review.mkdir(exist_ok=True)
        if m.review:
            (review / "peer_review.json").write_text(dumps(m.review), encoding="utf-8")
            written.append("review/peer_review.json")
        if critiques:
            (review / "figure_critiques.json").write_text(
                dumps(critiques), encoding="utf-8"
            )
            written.append("review/figure_critiques.json")
    return written


def _is_json(b: bytes) -> bool:
    try:
        return isinstance(json.loads(b.decode("utf-8")), dict)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False


def provenance(m: Materials, model: str) -> dict[str, Any]:
    """How the paper came about: the campaign, its budget, its guard decisions and, per
    finding, the chain of nodes it rests on."""
    nodes = {n["id"]: n for n in m.nodes}
    return {
        "campaign": {
            "id": str(m.campaign["id"]),
            "research_question": m.campaign.get("research_question"),
            "status": m.campaign["status"],
            "created_at": _jsonable(m.usage.get("created_at")),
            # The last change to the research graph (exports never touch it).
            "completed_at": _jsonable(
                max((n["updated_at"] for n in m.nodes), default=None)
            ),
        },
        "model": model,
        # Token totals are left out: formatting a package is charged to the campaign too,
        # so they would differ between exports of the same paper.
        "usage": {"compute_seconds_used": m.usage.get("gpu_seconds_used")},
        "findings": [
            {
                "id": str(f["id"]),
                "title": f["title"],
                "status": f["status"],
                "confidence": _jsonable(f["confidence_score"]),
                "lineage": [
                    {
                        "id": str(i),
                        "type": nodes[i]["node_type"],
                        "title": nodes[i]["title"],
                    }
                    for i in m.lineage.get(f["id"], [])
                    if i in nodes
                ],
            }
            for f in m.nodes
            if f["node_type"] == "finding"
        ],
        "guard_events": [
            {k: _jsonable(v) for k, v in g.items() if k != "detail"}
            for g in m.guard_events
        ],
        "user_documents": [
            {
                "name": d["canonical_name"],
                "file": (d.get("metadata") or {}).get("file_name"),
            }
            for d in m.user_documents
        ],
    }
