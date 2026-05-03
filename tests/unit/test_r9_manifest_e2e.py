"""Iter 18 — end-to-end test for R9 prompt-hash recording.

The iter-15 hook (``_record_prompt_hash``) is unit-tested in
``tests/unit/test_prompt_hash_recording.py`` against a fake recorder.
The iter-16 backfill threaded ``node_name=`` into all 23 LLM_call
sites. What was missing is a test that wires the *real*
``ManifestRecorder`` into a *real* ``LLM_call`` invocation and checks
the manifest gets the hash AND that hash is flushed to disk.

This test fills that gap: it exercises the full recorder-and-hash path
from ``LLM_call(... node_name="...")`` through ``ManifestRecorder.update``
through ``flush()`` to the on-disk ``manifest.json``. If anyone ever
breaks the hand-off between the LLM call site and the recorder, this
test goes red.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from plato.state.manifest import ManifestRecorder


def _build_state(
    project_dir: Path,
    *,
    recorder: ManifestRecorder | None,
    fake_llm: Any,
) -> dict[str, Any]:
    """Build the minimal state dict the LLM_call helpers expect.

    The helpers access:
      - ``state['llm']['llm']`` — the LangChain client (mocked here)
      - ``state['llm']['max_output_tokens']`` — for the warn check
      - ``state['tokens']`` — accumulator dict
      - ``state['files']['LLM_calls']`` — append-log path
      - ``state['files']['f_stream']`` — streaming output path (LLM_call_stream only)
      - ``state['recorder']`` — the optional ManifestRecorder
    """
    return {
        "llm": {"llm": fake_llm, "max_output_tokens": 1_000_000, "stream_verbose": False},
        "tokens": {"i": 0, "o": 0, "ti": 0, "to": 0},
        "files": {
            "LLM_calls": str(project_dir / "llm_calls.txt"),
            "f_stream": str(project_dir / "stream.txt"),
        },
        "recorder": recorder,
    }


def _fake_llm_with_invoke(reply: str = "ok") -> Any:
    """Return an object whose ``.invoke(prompt)`` returns a fake message.

    The reply object mimics the LangChain ``BaseMessage`` shape that
    ``LLM_call`` reads — ``.content`` and ``.usage_metadata`` (a dict
    with ``input_tokens`` / ``output_tokens``).
    """
    fake_message = SimpleNamespace(
        content=reply,
        usage_metadata={"input_tokens": 12, "output_tokens": 34},
    )

    class _FakeLLM:
        def invoke(self, prompt: Any) -> SimpleNamespace:  # noqa: D401
            return fake_message

    return _FakeLLM()


def test_real_recorder_receives_prompt_hash_and_flushes_to_disk(tmp_path: Path) -> None:
    """End-to-end: LLM_call → recorder.update → manifest.json on disk."""
    from plato.paper_agents.tools import LLM_call

    project = tmp_path / "project"
    project.mkdir()

    recorder = ManifestRecorder.start(
        project_dir=project,
        workflow="iter18-e2e-test",
        domain="astro",
        run_id="r9-e2e-fixture",
    )

    state = _build_state(project, recorder=recorder, fake_llm=_fake_llm_with_invoke())
    prompt = "Explain dark matter halo profiles in 50 words."

    LLM_call(prompt, state, node_name="literature_summary")

    # In-memory manifest has the hash.
    expected = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert recorder.manifest.prompt_hashes == {"literature_summary": expected}

    # On-disk manifest.json has the hash too — proves flush() was called.
    on_disk = json.loads(recorder.path.read_text())
    assert on_disk["prompt_hashes"] == {"literature_summary": expected}


def test_multiple_node_calls_accumulate_distinct_hashes(tmp_path: Path) -> None:
    """Two node calls under the same recorder must produce two manifest entries."""
    from plato.paper_agents.tools import LLM_call

    project = tmp_path / "project"
    project.mkdir()

    recorder = ManifestRecorder.start(
        project_dir=project,
        workflow="iter18-multi",
        run_id="r9-multi-fixture",
    )

    state = _build_state(project, recorder=recorder, fake_llm=_fake_llm_with_invoke())
    LLM_call("prompt-A", state, node_name="idea_maker")
    LLM_call("prompt-B", state, node_name="idea_hater")

    hashes = recorder.manifest.prompt_hashes
    assert set(hashes) == {"idea_maker", "idea_hater"}
    assert hashes["idea_maker"] == hashlib.sha256(b"prompt-A").hexdigest()
    assert hashes["idea_hater"] == hashlib.sha256(b"prompt-B").hexdigest()


def test_call_without_node_name_does_not_pollute_manifest(tmp_path: Path) -> None:
    """Legacy callers that don't pass node_name must not write empty entries."""
    from plato.paper_agents.tools import LLM_call

    project = tmp_path / "project"
    project.mkdir()

    recorder = ManifestRecorder.start(
        project_dir=project,
        workflow="iter18-no-name",
        run_id="r9-noname-fixture",
    )

    state = _build_state(project, recorder=recorder, fake_llm=_fake_llm_with_invoke())
    LLM_call("anything", state)  # no node_name

    assert recorder.manifest.prompt_hashes == {}


def test_call_without_recorder_is_silent_noop(tmp_path: Path) -> None:
    """A node_name without a recorder must not crash the LLM call path."""
    from plato.paper_agents.tools import LLM_call

    project = tmp_path / "project"
    project.mkdir()

    state = _build_state(project, recorder=None, fake_llm=_fake_llm_with_invoke())
    # No exception expected; nothing to write.
    LLM_call("hello", state, node_name="solo_run")


def test_recorder_failure_is_swallowed_so_paper_run_proceeds(tmp_path: Path) -> None:
    """A recorder whose ``update`` raises must not abort the LLM call.

    Reproducibility manifests are best-effort — losing the manifest is
    bad, but losing the actual paper run because the manifest had a
    transient write failure is worse.
    """
    from plato.paper_agents.tools import LLM_call

    project = tmp_path / "project"
    project.mkdir()

    class _BadRecorder:
        # Mimics the duck-typed surface the hook reads: just .update().
        def update(self, **fields: Any) -> None:
            raise RuntimeError("disk full")

    state = _build_state(project, recorder=_BadRecorder(), fake_llm=_fake_llm_with_invoke())
    # Must not raise.
    _, content = LLM_call("hello", state, node_name="will_fail")
    assert content == "ok"


@pytest.fixture(autouse=True)
def _enable_warnings_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    # Suppress the "Max output tokens" stdout noise from LLM_call when
    # running under pytest -q. The fake messages return real numbers so
    # the warning shouldn't fire, but pin the budget high just in case.
    monkeypatch.setenv("PLATO_TEST_QUIET", "1")
