"""Phase 5 — ``Plato.get_results`` dispatches via the Executor registry.

The previous implementation hard-wired :class:`plato.experiment.Experiment`
(and therefore ``cmbagent``). After the refactor, ``get_results`` must:

1. Look up an executor via the registry — ``executor=`` arg first, falling
   back to ``self.domain.executor``.
2. Forward ``research_idea``, ``methodology``, ``data_description``,
   ``project_dir``, and ``keys`` as kwargs.
3. Map :class:`~plato.executor.ExecutorResult` back onto
   ``self.research.results`` / ``self.research.plot_paths``.
4. Persist results to ``input_files/results.md``.

These tests register a recording fake executor and assert all four
behaviours without ever touching cmbagent.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from plato.config import INPUT_FILES, RESULTS_FILE
from plato.domain import DomainProfile
from plato.executor import EXECUTOR_REGISTRY, ExecutorResult, register_executor
from plato.plato import Plato


class _RecordingExecutor:
    """Records the kwargs ``Plato.get_results`` dispatches with."""

    def __init__(self, name: str, plot_paths: list[str] | None = None) -> None:
        self.name = name
        self.calls: list[dict[str, Any]] = []
        self._plot_paths = plot_paths or []

    async def run(self, **kwargs: Any) -> ExecutorResult:
        self.calls.append(kwargs)
        return ExecutorResult(
            results=f"# results from {self.name}\n",
            plot_paths=list(self._plot_paths),
        )


@pytest.fixture
def recording_executor():
    """Register a fake executor and clean it up after the test."""
    name = "fake-recording-executor"
    fake = _RecordingExecutor(name)
    register_executor(fake, overwrite=True)
    try:
        yield fake
    finally:
        EXECUTOR_REGISTRY.pop(name, None)


def _seed_inputs(plato: Plato, *, idea: str, method: str, description: str) -> None:
    """Drop the three input markdown files Plato reads in get_results()."""
    plato.research.idea = idea
    plato.research.methodology = method
    plato.research.data_description = description


def test_explicit_executor_kwarg_routes_to_registered_backend(
    tmp_path: Path, recording_executor: _RecordingExecutor
) -> None:
    plato = Plato(project_dir=str(tmp_path))
    _seed_inputs(plato, idea="my idea", method="my method", description="my data")

    plato.get_results(executor=recording_executor.name)

    assert len(recording_executor.calls) == 1
    call = recording_executor.calls[0]
    assert call["research_idea"] == "my idea"
    assert call["methodology"] == "my method"
    assert call["data_description"] == "my data"
    assert call["project_dir"] == plato.project_dir
    assert call["keys"] is plato.keys

    # Result mapped back onto the Research object.
    assert plato.research.results.startswith("# results from")
    assert plato.research.plot_paths == []

    # Persisted to input_files/results.md.
    results_file = Path(plato.project_dir) / INPUT_FILES / RESULTS_FILE
    assert results_file.read_text().startswith("# results from")


def test_domain_default_executor_is_used_when_kwarg_omitted(
    tmp_path: Path, recording_executor: _RecordingExecutor
) -> None:
    custom_domain = DomainProfile(
        name="phase5-test-domain",
        retrieval_sources=[],
        executor=recording_executor.name,
    )
    plato = Plato(project_dir=str(tmp_path), domain=custom_domain)
    _seed_inputs(plato, idea="i2", method="m2", description="d2")

    plato.get_results()  # no executor kwarg => DomainProfile.executor wins

    assert len(recording_executor.calls) == 1
    assert recording_executor.calls[0]["research_idea"] == "i2"


def test_explicit_executor_overrides_domain_default(
    tmp_path: Path, recording_executor: _RecordingExecutor
) -> None:
    """An explicit ``executor=`` kwarg must beat the domain default."""
    other = _RecordingExecutor("other-recording-executor")
    register_executor(other, overwrite=True)
    try:
        domain = DomainProfile(
            name="phase5-test-domain-override",
            retrieval_sources=[],
            executor=other.name,
        )
        plato = Plato(project_dir=str(tmp_path), domain=domain)
        _seed_inputs(plato, idea="i3", method="m3", description="d3")

        plato.get_results(executor=recording_executor.name)

        assert len(recording_executor.calls) == 1
        assert other.calls == []
    finally:
        EXECUTOR_REGISTRY.pop(other.name, None)


def test_unknown_executor_raises_clear_error(tmp_path: Path) -> None:
    plato = Plato(project_dir=str(tmp_path))
    _seed_inputs(plato, idea="i", method="m", description="d")

    with pytest.raises(KeyError, match="Unknown executor"):
        plato.get_results(executor="this-executor-does-not-exist")


def test_plot_paths_are_moved_into_plots_folder(
    tmp_path: Path, recording_executor: _RecordingExecutor
) -> None:
    """Backwards-compat: the legacy plot-relocation behaviour still runs."""
    plot_src = tmp_path / "scratch.png"
    plot_src.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    name = "plot-emitting-fake-executor"
    fake = _RecordingExecutor(name, plot_paths=[str(plot_src)])
    register_executor(fake, overwrite=True)
    try:
        project_dir = tmp_path / "proj"
        plato = Plato(project_dir=str(project_dir))
        _seed_inputs(plato, idea="i", method="m", description="d")

        plato.get_results(executor=name)

        # The original file should have been moved into plots_folder.
        assert not plot_src.exists()
        moved = Path(plato.plots_folder) / "scratch.png"
        assert moved.exists()
        assert plato.research.plot_paths == [str(plot_src)]
    finally:
        EXECUTOR_REGISTRY.pop(name, None)


def test_get_results_does_not_import_cmbagent_when_using_fake(
    tmp_path: Path, recording_executor: _RecordingExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mock ``Experiment.run_experiment`` to fail loudly if dispatch ever
    falls back to the cmbagent path. Then drive a non-cmbagent executor and
    confirm the mock is *not* hit."""
    import plato.experiment as plato_experiment

    def _explode(self, *a, **kw):  # noqa: ANN001
        raise AssertionError(
            "Experiment.run_experiment should not be called when dispatching "
            "to a non-cmbagent executor."
        )

    monkeypatch.setattr(
        plato_experiment.Experiment, "run_experiment", _explode, raising=True
    )

    plato = Plato(project_dir=str(tmp_path))
    _seed_inputs(plato, idea="i", method="m", description="d")
    plato.get_results(executor=recording_executor.name)

    assert len(recording_executor.calls) == 1
