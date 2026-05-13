"""Iter-25 — pin that ``run_manager.start_run`` honors a per-call
``project_dir`` override and that downstream helpers consult the
``_run_dirs`` registry.

The iter-24 entry-point guard already blocks cross-tenant launches at
the API server. Iter-25 adds defense-in-depth: even when ``start_run``
is invoked directly (CLI, tests, or a future endpoint that misses the
guard), the worker writes events / status / artifacts under whatever
``project_dir`` the caller passed — not into the legacy
``settings.project_root / project_id`` tree. These tests pin that
contract via direct calls to the helpers, with the heavy
multiprocessing path stubbed out.
"""
from __future__ import annotations

from pathlib import Path
import pytest


def test_normalize_model_config_prefers_openai_when_google_is_present() -> None:
    from plato_dashboard.worker import run_manager as rm

    config = {"mode": "fast", "models": {}}

    normalized = rm._normalize_model_config_for_keys(
        config,
        {"OPENAI_API_KEY": "openai-key", "GOOGLE_API_KEY": "google-key"},
    )

    assert normalized["models"]["llm"] == "gpt-4.1-mini"
    assert config["models"] == {}


def test_normalize_model_config_preserves_explicit_llm() -> None:
    from plato_dashboard.worker import run_manager as rm

    config = {"models": {"llm": "gemini-2.5-flash"}}

    normalized = rm._normalize_model_config_for_keys(
        config,
        {"OPENAI_API_KEY": "openai-key"},
    )

    assert normalized is config
    assert normalized["models"]["llm"] == "gemini-2.5-flash"


def test_run_dir_uses_registry_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When _run_dirs has an entry for run_id, _run_dir uses that base."""
    from plato_dashboard.worker import run_manager as rm

    # Register an override pointing at a per-user namespaced path.
    namespaced_root = tmp_path / "users" / "alice" / "myproj"
    namespaced_root.mkdir(parents=True)
    rm._run_dirs["test_run_42"] = namespaced_root

    try:
        path = rm._run_dir("myproj", "test_run_42")
    finally:
        rm._run_dirs.pop("test_run_42", None)

    expected = namespaced_root / "runs" / "test_run_42"
    assert path == expected
    assert path.is_dir()


def test_run_dir_falls_back_to_settings_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No registry entry → legacy settings.project_root resolution."""
    from plato_dashboard.worker import run_manager as rm
    from plato_dashboard.settings import Settings

    legacy_root = tmp_path / "legacy_root"
    legacy_root.mkdir()

    # Patch get_settings() to return a settings whose project_root is
    # legacy_root, then call _run_dir without registering an override.
    fake_settings = Settings(project_root=legacy_root)
    monkeypatch.setattr(rm, "get_settings", lambda: fake_settings)

    path = rm._run_dir("project_x", "run_legacy")
    expected = legacy_root / "project_x" / "runs" / "run_legacy"
    assert path == expected


def test_explicit_project_dir_override_beats_registry(
    tmp_path: Path,
) -> None:
    """An explicit project_dir kwarg must win over a stale registry entry."""
    from plato_dashboard.worker import run_manager as rm

    stale = tmp_path / "stale_namespace"
    stale.mkdir()
    fresh = tmp_path / "fresh_namespace"
    fresh.mkdir()

    rm._run_dirs["test_run_explicit"] = stale
    try:
        path = rm._run_dir("proj", "test_run_explicit", project_dir=fresh)
    finally:
        rm._run_dirs.pop("test_run_explicit", None)

    expected = fresh / "runs" / "test_run_explicit"
    assert path == expected
    # Stale entry must NOT have been touched.
    assert not (stale / "runs").exists()


def test_events_path_and_status_path_share_resolution(tmp_path: Path) -> None:
    """_events_path and _status_path must agree with _run_dir on the base."""
    from plato_dashboard.worker import run_manager as rm

    namespaced = tmp_path / "users" / "bob" / "proj"
    namespaced.mkdir(parents=True)
    rm._run_dirs["agree_run"] = namespaced
    try:
        events = rm._events_path("proj", "agree_run")
        status = rm._status_path("proj", "agree_run")
    finally:
        rm._run_dirs.pop("agree_run", None)

    assert events.parent == status.parent
    assert events.parent == namespaced / "runs" / "agree_run"
    assert events.name == "events.jsonl"
    assert status.name == "status.json"


def test_resolve_project_dir_iterates_registry_by_project_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When only project_id is in scope, _resolve_project_dir scans
    ``_run_dirs`` for a matching active run, falling back to legacy
    resolution when nothing matches."""
    from plato_dashboard.worker import run_manager as rm
    from plato_dashboard.domain.models import Run, utcnow
    from plato_dashboard.settings import Settings

    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    monkeypatch.setattr(
        rm, "get_settings", lambda: Settings(project_root=legacy_root)
    )

    namespaced = tmp_path / "users" / "alice" / "tenanted_proj"
    namespaced.mkdir(parents=True)

    # Register an active Run + its project_dir override.
    fake_run = Run(
        id="active_run", project_id="tenanted_proj", stage="idea", started_at=utcnow()
    )
    rm._active_runs["active_run"] = fake_run
    rm._run_dirs["active_run"] = namespaced

    try:
        # Hit the registry path — project_id matches an active run.
        resolved = rm._resolve_project_dir("tenanted_proj")
        assert resolved == namespaced

        # No active run for "untracked" → fall back to settings.
        resolved_fallback = rm._resolve_project_dir("untracked")
        assert resolved_fallback == legacy_root / "untracked"
    finally:
        rm._active_runs.pop("active_run", None)
        rm._run_dirs.pop("active_run", None)


def test_cancel_run_clears_run_dirs_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``cancel_run`` must drop the registry entry so a stale path
    doesn't leak into a subsequent run with the same id."""
    import asyncio
    from plato_dashboard.worker import run_manager as rm
    from plato_dashboard.domain.models import Run, utcnow

    fake_run = Run(
        id="cancel_target",
        project_id="proj",
        stage="idea",
        status="running",
        started_at=utcnow(),
    )
    rm._active_runs["cancel_target"] = fake_run
    rm._run_dirs["cancel_target"] = tmp_path / "ephemeral"
    (tmp_path / "ephemeral").mkdir()

    try:
        # ``cancel_run`` is async. We don't actually have a subprocess
        # or supervise task; cancel_run handles missing entries
        # gracefully.
        result = asyncio.run(rm.cancel_run("cancel_target"))
        assert result is True
        # The override entry must be gone.
        assert "cancel_target" not in rm._run_dirs
    finally:
        rm._active_runs.pop("cancel_target", None)
        rm._run_dirs.pop("cancel_target", None)


def test_project_run_lifecycle_updates_meta_from_artifact(tmp_path: Path) -> None:
    """Run finalization should clear active_run and mark a stage done only
    when the canonical artifact exists."""
    from plato_dashboard.domain.models import Project, Run, utcnow
    from plato_dashboard.worker import run_manager as rm

    project = Project.empty(name="Lifecycle")
    project.id = "proj_lifecycle"
    project_dir = tmp_path / project.id
    (project_dir / "input_files").mkdir(parents=True)
    (project_dir / "meta.json").write_text(project.model_dump_json())

    run = Run(
        id="run_lifecycle",
        project_id=project.id,
        stage="idea",
        status="running",
        started_at=utcnow(),
        config={"models": {"llm": "gpt-4.1-mini"}},
    )

    rm._set_project_run_started(run, project_dir)
    started = Project.model_validate_json((project_dir / "meta.json").read_text())
    assert started.active_run is not None
    assert started.active_run.run_id == run.id
    assert started.stages["idea"].status == "running"

    (project_dir / "input_files" / "idea.md").write_text("Test idea")
    run.status = "succeeded"
    run.finished_at = utcnow()
    rm._set_project_run_finished(run, project_dir)

    finished = Project.model_validate_json((project_dir / "meta.json").read_text())
    assert finished.active_run is None
    assert finished.stages["idea"].status == "done"
    assert finished.stages["idea"].origin == "ai"
    assert finished.stages["idea"].model == "gpt-4.1-mini"


def test_project_run_success_without_artifact_becomes_failed(tmp_path: Path) -> None:
    """A subprocess exit code of 0 is not enough for a successful stage."""
    from plato_dashboard.domain.models import Project, Run, utcnow
    from plato_dashboard.worker import run_manager as rm

    project = Project.empty(name="Missing artifact")
    project.id = "proj_missing_artifact"
    project_dir = tmp_path / project.id
    (project_dir / "input_files").mkdir(parents=True)
    (project_dir / "meta.json").write_text(project.model_dump_json())

    run = Run(
        id="run_missing_artifact",
        project_id=project.id,
        stage="idea",
        status="succeeded",
        started_at=utcnow(),
        finished_at=utcnow(),
    )

    rm._set_project_run_finished(run, project_dir)

    finished = Project.model_validate_json((project_dir / "meta.json").read_text())
    assert run.status == "failed"
    assert "without writing the expected artifact" in (run.error or "")
    assert finished.stages["idea"].status == "failed"


def test_results_executor_selector_prefers_explicit_config(tmp_path: Path) -> None:
    from plato_dashboard.worker import run_manager as rm

    assert (
        rm._select_results_executor(
            tmp_path,
            {"executor": "local_jupyter"},
            {"executor": "sklearn_synthetic"},
        )
        == "local_jupyter"
    )


def test_results_executor_selector_prefers_explicit_extra(tmp_path: Path) -> None:
    from plato_dashboard.worker import run_manager as rm

    assert rm._select_results_executor(tmp_path, {}, {"executor": "e2b"}) == "e2b"


def test_results_executor_selector_detects_no_upload_synthetic_tabular_project(
    tmp_path: Path,
) -> None:
    from plato_dashboard.worker import run_manager as rm

    input_dir = tmp_path / "input_files"
    input_dir.mkdir()
    (input_dir / "data_description.md").write_text(
        "Synthetic tabular ML dataset with 600 rows and binary classification."
    )
    (input_dir / "idea.md").write_text(
        "Compare logistic regression and random forest ROC-AUC and calibration."
    )
    (input_dir / "methods.md").write_text(
        "Use stratified cross-validation and feature-effect analysis."
    )

    assert rm._select_results_executor(tmp_path, {}, {}) == "sklearn_synthetic"


def test_results_executor_selector_does_not_override_data_file_projects(
    tmp_path: Path,
) -> None:
    from plato_dashboard.worker import run_manager as rm

    input_dir = tmp_path / "input_files"
    input_dir.mkdir()
    (input_dir / "data_description.md").write_text(
        "Synthetic tabular classification dataset:\n"
        "- /tmp/does-not-exist-plato-input.csv"
    )
    (input_dir / "idea.md").write_text("Compare random forest and logistic regression.")
    (input_dir / "methods.md").write_text("Evaluate ROC-AUC.")

    assert rm._select_results_executor(tmp_path, {}, {}) is None
