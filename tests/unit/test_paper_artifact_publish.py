from __future__ import annotations

import zipfile
from pathlib import Path

from plato.plato import Plato


def test_publish_paper_artifacts_requires_citation_bearing_draft(tmp_path: Path):
    plato = Plato(project_dir=str(tmp_path))
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "paper_v2_no_citations.tex").write_text("draft", encoding="utf-8")
    (paper_dir / "paper_v2_no_citations.pdf").write_bytes(b"%PDF-1.5\n")

    try:
        plato._publish_paper_artifacts()
    except RuntimeError as exc:
        assert "citation-bearing" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("no-citation draft was promoted")


def test_publish_paper_artifacts_creates_submission_zip(tmp_path: Path):
    plato = Plato(project_dir=str(tmp_path))
    paper_dir = tmp_path / "paper"
    run_dir = tmp_path / "runs" / "run-test"
    plot_dir = tmp_path / "input_files" / "plots"
    paper_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    (paper_dir / "paper_v3_citations.tex").write_text("cited tex", encoding="utf-8")
    (paper_dir / "paper_v3_citations.pdf").write_bytes(b"%PDF-1.5\n")
    (paper_dir / "bibliography.bib").write_text("@article{a}", encoding="utf-8")
    (paper_dir / "scientific_verification.json").write_text("{}", encoding="utf-8")
    (run_dir / "validation_report.json").write_text("{}", encoding="utf-8")
    (plot_dir / "figure.png").write_bytes(b"png")

    plato._publish_paper_artifacts()

    package = paper_dir / "submission_package.zip"
    assert (paper_dir / "main.tex").read_text(encoding="utf-8") == "cited tex"
    assert package.is_file()
    with zipfile.ZipFile(package) as zf:
        names = set(zf.namelist())

    assert "main.tex" in names
    assert "main.pdf" in names
    assert "bibliography.bib" in names
    assert "reports/paper-scientific_verification.json" in names
    assert "reports/run-test-validation_report.json" in names
    assert "figures/input_files/plots/figure.png" in names
    assert "README_SUBMISSION.md" in names
