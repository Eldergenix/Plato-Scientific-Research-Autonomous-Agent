from __future__ import annotations

from pathlib import Path

import pytest

from plato.plato import Plato


def _make_plato(tmp_path: Path) -> Plato:
    return Plato(project_dir=str(tmp_path))


def test_require_model_credentials_reports_missing_openai_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    plato = _make_plato(tmp_path)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        plato._require_model_credentials("gpt-4.1-mini")


def test_require_model_credentials_reports_multiple_missing_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    plato = _make_plato(tmp_path)

    with pytest.raises(RuntimeError) as excinfo:
        plato._require_model_credentials("gpt-4.1-mini", "gemini-2.5-flash")

    message = str(excinfo.value)
    assert "OPENAI_API_KEY" in message
    assert "GOOGLE_API_KEY" in message


def test_get_paper_fails_fast_before_graph_without_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    plato = _make_plato(tmp_path)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        plato.get_paper(llm="gpt-4.1-mini", add_citations=False)


def test_get_results_allows_sklearn_synthetic_without_hosted_model_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    plato = _make_plato(tmp_path)
    plato.research.data_description = "Synthetic binary classification benchmark."
    plato.research.idea = "Compare calibrated classifiers on synthetic tabular data."
    plato.research.methodology = "Use deterministic synthetic data and report cross-validated metrics."

    plato.get_results(executor="sklearn_synthetic")

    assert "roc_auc" in plato.research.results.lower()
    assert plato.research.plot_paths
