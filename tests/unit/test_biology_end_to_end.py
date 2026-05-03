"""Phase 5: biology DomainProfile end-to-end smoke through EvalRunner.

Mirrors the _FakePlato pattern from test_eval_runner.py, but:

1. Asserts the biology DomainProfile resolves correctly when Plato is
   instantiated with ``domain="biology"``.
2. Drives the runner against the protein_structure_alphafold golden task
   with a fake Plato that records the resolved domain and writes a
   manifest carrying ``domain="biology"``.
3. Confirms the fake retrieval call only sees the biology adapter set
   (``pubmed`` / ``openalex`` / ``semantic_scholar``) — never astro
   adapters like ``arxiv`` or ``ads``.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evals import EvalRunner
from evals.tasks import GoldenTask, load_task
from plato.domain import DomainProfile, get_domain


REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "evals" / "golden"
PROTEIN_TASK_PATH = GOLDEN_DIR / "protein_structure_alphafold.json"


# Astro-only adapter names. If any of these leak into a biology run we
# must fail loudly — that's a regression of the domain-routed retrieval.
ASTRO_ONLY_ADAPTERS = {"arxiv", "ads"}


class _FakeBiologyPlato:
    """Mock Plato that resolves a DomainProfile and records adapter use.

    Matches the _FakePlato shape in tests/unit/test_eval_runner.py, but
    additionally:

    * Resolves ``domain`` via ``get_domain`` exactly like the real
      ``Plato.__init__`` so we can assert the biology profile lands
      end-to-end.
    * Records every retrieval source the fake "tool" was asked about,
      so the test can assert the call set is biology-restricted.
    * Stamps ``domain`` into every emitted manifest so the runner's
      aggregator sees the right value.
    """

    def __init__(
        self,
        project_dir: Path,
        *,
        domain: str | DomainProfile = "biology",
        tokens_per_call: int = 100,
        cost_per_call: float = 0.01,
        latency_per_call: float = 0.5,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.domain: DomainProfile = (
            domain if isinstance(domain, DomainProfile) else get_domain(domain)
        )
        self.tokens_per_call = tokens_per_call
        self.cost_per_call = cost_per_call
        self.latency_per_call = latency_per_call
        self.calls: list[str] = []
        self.retrieval_sources_seen: list[str] = []

    def _emit_manifest(self, workflow: str) -> None:
        run_id = uuid.uuid4().hex[:12]
        run_dir = self.project_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc)
        ended = started + timedelta(seconds=self.latency_per_call)
        payload = {
            "run_id": run_id,
            "workflow": workflow,
            "started_at": started.isoformat(),
            "ended_at": ended.isoformat(),
            "status": "success",
            "tokens_in": self.tokens_per_call,
            "tokens_out": self.tokens_per_call // 2,
            "cost_usd": self.cost_per_call,
            "domain": self.domain.name,
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True)
        )

    def _fake_retrieve(self) -> None:
        """Stand-in for retrieval — records which adapters the domain exposes."""
        for src in self.domain.retrieval_sources:
            self.retrieval_sources_seen.append(src)

    def set_data_description(self, data_description: str) -> None:
        self.calls.append("set_data_description")

    def get_idea(self, mode: str = "fast") -> None:
        self.calls.append(f"get_idea:{mode}")
        self._fake_retrieve()
        self._emit_manifest("get_idea_fast")

    def get_method(self, mode: str = "fast") -> None:
        self.calls.append(f"get_method:{mode}")
        self._fake_retrieve()
        self._emit_manifest("get_method_fast")


def test_biology_domain_resolves_through_plato_init_path():
    """Constructing a Plato-shaped object with domain='biology' resolves the right profile."""
    plato = _FakeBiologyPlato(Path("/tmp/unused-for-init-check"), domain="biology")
    assert plato.domain.name == "biology"
    assert plato.domain.retrieval_sources == ["pubmed", "openalex", "semantic_scholar"]
    assert plato.domain.keyword_extractor == "mesh"
    assert plato.domain.novelty_corpus == "pubmed"


def test_biology_profile_journal_presets_match_spec():
    """Sanity-check the §5.5 journal preset list at the source of truth."""
    biology = get_domain("biology")
    assert biology.journal_presets == [
        "NATURE", "CELL", "SCIENCE", "PLOS_BIO", "ELIFE", "NONE",
    ]


def test_protein_structure_task_has_biology_domain():
    """The shipped protein_structure_alphafold.json is a biology task."""
    task = load_task(PROTEIN_TASK_PATH)
    assert task.domain == "biology"
    assert "AlphaFold" in task.expected_idea_keywords
    # Gold sources must include the AlphaFold paper DOI (per spec).
    assert "10.1038/s41586-021-03819-2" in [gs.doi for gs in task.gold_sources]


def test_eval_runner_biology_end_to_end_writes_manifest_with_biology_domain(
    tmp_path: Path,
) -> None:
    """Full smoke: protein task → biology Plato → manifest tagged biology."""
    task = load_task(PROTEIN_TASK_PATH)
    runner = EvalRunner(
        [task],
        output_dir=tmp_path / "results",
        max_cost_usd=10.0,
    )

    built: list[_FakeBiologyPlato] = []

    def factory(_task: GoldenTask, project_dir: Path) -> _FakeBiologyPlato:
        # The runner is what wires task → factory → Plato; the biology
        # profile arrives via the explicit domain= arg, mirroring the
        # production path where set the domain at Plato construction time.
        plato = _FakeBiologyPlato(project_dir, domain=_task.domain)
        built.append(plato)
        return plato

    results = asyncio.run(runner.run(factory))

    # 1) Pipeline ran cleanly, metrics recorded, no tool errors.
    assert set(results.keys()) == {"protein_structure_alphafold"}
    metrics = results["protein_structure_alphafold"]
    assert metrics.tokens_in == 200  # 2 calls * 100
    assert metrics.tokens_out == 100  # 2 calls * 50
    assert metrics.tool_call_error_rate is None

    # 2) The Plato instance the runner built actually resolved to biology.
    assert len(built) == 1
    assert built[0].domain.name == "biology"

    # 3) Every manifest the runner aggregated is stamped domain=biology.
    project_dir = tmp_path / "results" / "protein_structure_alphafold" / "project"
    manifests = sorted((project_dir / "runs").glob("*/manifest.json"))
    assert len(manifests) == 2  # get_idea + get_method
    for path in manifests:
        payload = json.loads(path.read_text())
        assert payload["domain"] == "biology", (
            f"manifest {path} expected domain=biology, got {payload.get('domain')!r}"
        )


def test_eval_runner_biology_run_only_uses_biology_adapters(tmp_path: Path) -> None:
    """Retrieval during a biology run must NEVER touch astro-only adapters."""
    task = load_task(PROTEIN_TASK_PATH)
    runner = EvalRunner(
        [task],
        output_dir=tmp_path / "results",
        max_cost_usd=10.0,
    )

    captured: list[_FakeBiologyPlato] = []

    def factory(_task: GoldenTask, project_dir: Path) -> _FakeBiologyPlato:
        plato = _FakeBiologyPlato(project_dir, domain=_task.domain)
        captured.append(plato)
        return plato

    asyncio.run(runner.run(factory))

    assert len(captured) == 1
    sources = set(captured[0].retrieval_sources_seen)
    # The biology adapter set is exactly these three.
    assert sources == {"pubmed", "openalex", "semantic_scholar"}
    # And critically: no astro-only adapter ever got asked.
    leaked = sources & ASTRO_ONLY_ADAPTERS
    assert not leaked, (
        f"biology run leaked into astro-only adapters: {leaked}"
    )


def test_summary_json_includes_biology_task(tmp_path: Path) -> None:
    """The runner's summary.json carries the biology task id."""
    task = load_task(PROTEIN_TASK_PATH)
    runner = EvalRunner(
        [task],
        output_dir=tmp_path / "results",
        max_cost_usd=10.0,
    )

    def factory(_task: GoldenTask, project_dir: Path) -> _FakeBiologyPlato:
        return _FakeBiologyPlato(project_dir, domain=_task.domain)

    asyncio.run(runner.run(factory))

    summary = json.loads((tmp_path / "results" / "summary.json").read_text())
    assert summary["task_count"] == 1
    assert summary["task_ids"] == ["protein_structure_alphafold"]


@pytest.mark.parametrize(
    "domain_name,expected_sources",
    [
        ("astro", ["semantic_scholar", "arxiv", "openalex", "ads"]),
        ("biology", ["pubmed", "openalex", "semantic_scholar"]),
    ],
)
def test_domain_specific_adapter_sets_are_disjoint_in_unique_sources(
    domain_name: str, expected_sources: list[str]
) -> None:
    """Sanity guard: astro and biology profiles surface their declared adapter set."""
    profile = get_domain(domain_name)
    assert profile.retrieval_sources == expected_sources
