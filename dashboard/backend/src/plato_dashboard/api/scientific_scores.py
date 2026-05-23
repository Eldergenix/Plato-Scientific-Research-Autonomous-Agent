"""Project-level scientific scoring.

The dashboard needs quick guidance on whether a generated paper looks
original, impactful, and supported by its findings. This endpoint scores the
actual project artifacts on disk rather than a canned demo payload.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import extract_user_id
from ..domain.models import JsonObjectResponse
from ..settings import Settings, get_settings
from ..storage.project_store import ProjectStore


router = APIRouter()

MAX_TEXT_CHARS = 200_000

ORIGINALITY_TERMS = (
    "novel",
    "original",
    "new",
    "first",
    "previously",
    "prior work",
    "unexplored",
    "gap",
    "hypothesis",
    "signature",
    "framework",
    "mechanism",
)
IMPACT_TERMS = (
    "clinical",
    "patient",
    "public health",
    "decision",
    "actionable",
    "deployment",
    "benchmark",
    "screening",
    "risk",
    "intervention",
    "diagnostic",
    "policy",
)
FINDINGS_TERMS = (
    "accuracy",
    "auc",
    "f1",
    "precision",
    "recall",
    "p-value",
    "confidence interval",
    "cross-validation",
    "held-out",
    "test set",
    "calibration",
    "sensitivity",
    "specificity",
    "statistically",
    "effect size",
)
VALIDATION_TERMS = (
    "limitation",
    "reproduc",
    "validation",
    "bootstrap",
    "ablation",
    "error analysis",
    "robust",
    "seed",
    "train",
    "test",
)


def _project_store(settings: Settings, user_id: str | None) -> ProjectStore:
    root = settings.project_root if user_id is None else settings.project_root / "users" / user_id
    return ProjectStore(root, user_id=user_id)


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(errors="ignore")[:MAX_TEXT_CHARS]
    except OSError:
        return ""


def _term_hits(text: str, terms: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term in lower]


def _count_metric_mentions(text: str) -> int:
    patterns = (
        r"\b(?:auc|auroc|accuracy|f1|precision|recall|sensitivity|specificity)\b\s*(?:=|of|:)?\s*\d+(?:\.\d+)?%?",
        r"\bp\s*[<=>]\s*0?\.\d+",
        r"\b\d+(?:\.\d+)?\s*%",
        r"\bci\b|\bconfidence interval\b",
    )
    return sum(len(re.findall(pattern, text, flags=re.IGNORECASE)) for pattern in patterns)


def _sample_size_score(text: str) -> tuple[float, str | None]:
    matches = [
        int(m.group(1).replace(",", ""))
        for m in re.finditer(
            r"\b(\d{2,7}(?:,\d{3})*)\s+(?:rows|records|samples|observations|patients|cases|participants)\b",
            text,
            flags=re.IGNORECASE,
        )
    ]
    if not matches:
        return 0.0, None
    largest = max(matches)
    if largest >= 10_000:
        return 1.0, f"largest stated cohort or table size is {largest:,}"
    if largest >= 1_000:
        return 0.8, f"largest stated cohort or table size is {largest:,}"
    if largest >= 250:
        return 0.6, f"largest stated cohort or table size is {largest:,}"
    return 0.35, f"largest stated cohort or table size is {largest:,}"


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def _label(score: float) -> str:
    if score >= 0.8:
        return "Strong"
    if score >= 0.62:
        return "Promising"
    if score >= 0.42:
        return "Developing"
    return "Needs work"


def _axis(score: float, summary: str, signals: list[str], cautions: list[str]) -> dict[str, Any]:
    score = _clamp(score)
    return {
        "score": score,
        "label": _label(score),
        "summary": summary,
        "signals": signals[:5],
        "cautions": cautions[:4],
    }


def _score_project(project_dir: Path) -> dict[str, Any]:
    input_dir = project_dir / "input_files"
    plots_dir = input_dir / "plots"
    texts = {
        "data": _read_text(input_dir / "data_description.md"),
        "idea": _read_text(input_dir / "idea.md"),
        "literature": _read_text(input_dir / "literature.md"),
        "method": _read_text(input_dir / "methods.md"),
        "results": _read_text(input_dir / "results.md"),
        "paper": _read_text(project_dir / "paper" / "main.tex"),
    }
    all_text = "\n\n".join(texts.values())
    idea_and_lit = "\n\n".join([texts["idea"], texts["literature"], texts["paper"]])
    result_text = "\n\n".join([texts["results"], texts["paper"]])
    plot_count = len([p for p in plots_dir.glob("*") if p.is_file()]) if plots_dir.is_dir() else 0
    has_pdf = (project_dir / "paper" / "main.pdf").is_file()
    metric_mentions = _count_metric_mentions(result_text)
    sample_score, sample_signal = _sample_size_score(all_text)

    originality_hits = _term_hits(idea_and_lit, ORIGINALITY_TERMS)
    literature_present = bool(texts["literature"].strip())
    prior_work_present = any(term in idea_and_lit.lower() for term in ("prior", "existing", "literature", "related work"))
    originality_signals = []
    if originality_hits:
        originality_signals.append(f"novelty language: {', '.join(originality_hits[:4])}")
    if literature_present:
        originality_signals.append("literature stage is present")
    if prior_work_present:
        originality_signals.append("paper positions the idea against prior work")
    originality_cautions = []
    if not literature_present:
        originality_cautions.append("no literature artifact found, so novelty is weakly grounded")
    if len(originality_hits) < 2:
        originality_cautions.append("few explicit claims about what is new")
    originality_score = (
        0.28
        + min(len(originality_hits), 6) * 0.06
        + (0.18 if literature_present else 0.0)
        + (0.14 if prior_work_present else 0.0)
    )

    impact_hits = _term_hits(all_text, IMPACT_TERMS)
    impact_signals = []
    if sample_signal:
        impact_signals.append(sample_signal)
    if impact_hits:
        impact_signals.append(f"application language: {', '.join(impact_hits[:4])}")
    if metric_mentions:
        impact_signals.append(f"{metric_mentions} quantitative result mentions")
    impact_cautions = []
    if not sample_signal:
        impact_cautions.append("no explicit real-data sample size found")
    if len(impact_hits) < 2:
        impact_cautions.append("limited stated downstream use or stakeholder impact")
    impact_score = 0.24 + sample_score * 0.28 + min(len(impact_hits), 6) * 0.05 + min(metric_mentions, 8) * 0.035

    finding_hits = _term_hits(result_text, FINDINGS_TERMS)
    validation_hits = _term_hits(result_text, VALIDATION_TERMS)
    findings_signals = []
    if metric_mentions:
        findings_signals.append(f"{metric_mentions} quantitative metric mentions")
    if plot_count:
        findings_signals.append(f"{plot_count} generated plot artifact{'s' if plot_count != 1 else ''}")
    if validation_hits:
        findings_signals.append(f"validation language: {', '.join(validation_hits[:4])}")
    if has_pdf:
        findings_signals.append("compiled PDF artifact is present")
    findings_cautions = []
    if not texts["results"].strip():
        findings_cautions.append("results artifact is missing")
    if metric_mentions < 2:
        findings_cautions.append("few quantitative findings were detected")
    if not validation_hits:
        findings_cautions.append("validation and limitation language is sparse")
    findings_score = (
        0.18
        + min(metric_mentions, 10) * 0.055
        + min(plot_count, 4) * 0.055
        + min(len(finding_hits), 6) * 0.035
        + min(len(validation_hits), 5) * 0.035
        + (0.08 if has_pdf else 0.0)
    )

    axes = {
        "originality": _axis(
            originality_score,
            "How clearly the work appears differentiated from prior work.",
            originality_signals,
            originality_cautions,
        ),
        "impact": _axis(
            impact_score,
            "How likely the work is to matter beyond the experiment itself.",
            impact_signals,
            impact_cautions,
        ),
        "findings": _axis(
            findings_score,
            "How strongly the paper's claims are supported by concrete results.",
            findings_signals,
            findings_cautions,
        ),
    }
    overall_score = _clamp(
        axes["originality"]["score"] * 0.3
        + axes["impact"]["score"] * 0.32
        + axes["findings"]["score"] * 0.38
    )

    return {
        "overall": {
            "score": overall_score,
            "label": _label(overall_score),
            "summary": "Heuristic guidance from the project's real idea, literature, results, plots, and paper artifacts.",
        },
        "axes": axes,
        "inputs": {
            "has_data": bool(texts["data"].strip()),
            "has_idea": bool(texts["idea"].strip()),
            "has_literature": literature_present,
            "has_method": bool(texts["method"].strip()),
            "has_results": bool(texts["results"].strip()),
            "has_paper_tex": bool(texts["paper"].strip()),
            "has_paper_pdf": has_pdf,
            "plot_count": plot_count,
            "metric_mentions": metric_mentions,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/projects/{pid}/scientific-scores", response_model=JsonObjectResponse)
def get_scientific_scores(
    pid: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    store = _project_store(settings, extract_user_id(request))
    try:
        store.load(pid)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={"code": "project_not_found", "project_id": pid}) from exc
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "invalid_project_id", "project_id": pid}) from exc

    return _score_project(store.project_dir(pid))


__all__ = ["router"]
