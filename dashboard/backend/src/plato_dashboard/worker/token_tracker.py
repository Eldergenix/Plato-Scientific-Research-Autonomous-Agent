"""Token usage and cost tracker for Plato dashboard.

Pure data layer (no FastAPI). Reads per-stage ``LLM_calls.txt`` ledgers
written by Plato into ``<project_dir>/<stage>_generation_output/`` and
aggregates totals + cost. Also exposes a live in-memory ledger keyed by
run_id for streaming usage updates from the EventBus, with an
on-finish reconciliation step that prefers the canonical on-disk file.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..domain.models import StageId

# ---------------------------------------------------------------------------
# Cost table — mirrors dashboard/frontend/src/lib/models.ts (USD per 1k tokens).
# Update in tandem with the frontend MODELS array.
# ---------------------------------------------------------------------------

MODEL_COSTS: dict[str, tuple[float, float]] = {
    # Gemini
    "gemini-2.0-flash": (0.00010, 0.00040),
    "gemini-2.5-flash": (0.00030, 0.0025),
    "gemini-2.5-pro": (0.00125, 0.010),
    # OpenAI
    "o3-mini": (0.00110, 0.0044),
    "gpt-4o": (0.0025, 0.010),
    "gpt-4.1": (0.0020, 0.0080),
    "gpt-4.1-mini": (0.00040, 0.0016),
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4.5": (0.075, 0.150),
    "gpt-5": (0.0125, 0.050),
    "gpt-5-mini": (0.00025, 0.0020),
    # Anthropic
    "claude-3.7-sonnet": (0.003, 0.015),
    "claude-4-opus": (0.015, 0.075),
    "claude-4.1-opus": (0.015, 0.075),
}

# Stage outputs we walk on disk.
_STAGES: tuple[StageId, ...] = (
    "idea",
    "method",
    "results",  # mapped from experiment_generation_output below
    "literature",
    "paper",
    "referee",
)

# Plato writes "experiment_generation_output" for the results stage.
_STAGE_DIR_OVERRIDES: dict[str, str] = {"results": "experiment"}


# ---------------------------------------------------------------------------
# Model id normalization
# ---------------------------------------------------------------------------

_DATE_SUFFIX_RE = re.compile(r"-\d{6,8}$")


def normalize_model_id(raw: Optional[str]) -> Optional[str]:
    """Map a raw provider model id to a canonical key in MODEL_COSTS.

    Handles dated suffixes (e.g. ``claude-opus-4-1-20250805`` →
    ``claude-4.1-opus``) and a few naming reorderings between providers
    and Plato's display ids. Returns ``None`` if the input is empty.
    Returns the input unchanged if no rule applies — callers treat
    unknown models as zero-cost rather than crashing.
    """
    if not raw:
        return None
    m = raw.strip().lower()
    if not m:
        return None

    # Direct hit.
    if m in MODEL_COSTS:
        return m

    # Strip trailing date stamp (-YYYYMMDD or -YYMMDD).
    stripped = _DATE_SUFFIX_RE.sub("", m)
    if stripped in MODEL_COSTS:
        return stripped

    # Anthropic naming swap: claude-<family>-<major>-<minor> →
    # claude-<major>.<minor>-<family>. e.g. "claude-opus-4-1" → "claude-4.1-opus".
    am = re.match(r"^claude-([a-z]+)-(\d+)(?:-(\d+))?", stripped)
    if am:
        family, major, minor = am.group(1), am.group(2), am.group(3)
        version = f"{major}.{minor}" if minor else major
        candidate = f"claude-{version}-{family}"
        if candidate in MODEL_COSTS:
            return candidate

    # Common OpenAI aliases.
    aliases = {
        "gpt5": "gpt-5",
        "gpt-5-turbo": "gpt-5",
        "gpt-4-1": "gpt-4.1",
        "gpt-4-1-mini": "gpt-4.1-mini",
        "gpt-4-5": "gpt-4.5",
        "claude-3-7-sonnet": "claude-3.7-sonnet",
        "claude-4-1-opus": "claude-4.1-opus",
    }
    if stripped in aliases:
        return aliases[stripped]

    # Substring fallback: pick the longest registered key that appears in m.
    matches = [k for k in MODEL_COSTS if k in m]
    if matches:
        return max(matches, key=len)

    return raw  # unknown — preserved so callers can surface it


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StageTokens:
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_cents: int = 0

    def add(self, other: "StageTokens") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost_cents += other.cost_cents
        if self.model is None:
            self.model = other.model


@dataclass
class ProjectUsage:
    total_input: int = 0
    total_output: int = 0
    total_cost_cents: int = 0
    by_stage: dict[str, StageTokens] = field(default_factory=dict)
    by_model: dict[str, StageTokens] = field(default_factory=dict)
    by_run: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cost arithmetic
# ---------------------------------------------------------------------------


def estimate_cost_cents(model: Optional[str], input_tok: int, output_tok: int) -> int:
    """USD cost expressed in integer cents. Unknown model → 0."""
    canonical = normalize_model_id(model)
    rates = MODEL_COSTS.get(canonical or "")
    if not rates:
        return 0
    in_rate, out_rate = rates
    dollars = (in_rate * input_tok + out_rate * output_tok) / 1000.0
    return int(round(dollars * 100))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.\-]*)\s*=\s*([^\s]+)")


def _coerce_int(s: str) -> Optional[int]:
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _parse_kv_line(line: str) -> Optional[StageTokens]:
    pairs = dict(_KV_RE.findall(line))
    if not pairs:
        return None

    model = pairs.get("model") or pairs.get("model_id")
    # Per-call deltas preferred; fall back to totals only if no deltas.
    in_tok = _coerce_int(
        pairs.get("input_tokens") or pairs.get("prompt_tokens") or "0"
    )
    out_tok = _coerce_int(
        pairs.get("output_tokens") or pairs.get("completion_tokens") or "0"
    )
    if in_tok is None and out_tok is None:
        return None
    in_tok = in_tok or 0
    out_tok = out_tok or 0
    if in_tok == 0 and out_tok == 0:
        return None
    return StageTokens(
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_cents=estimate_cost_cents(model, in_tok, out_tok),
    )


def _parse_json_line(line: str) -> Optional[StageTokens]:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    model = obj.get("model") or obj.get("model_id")
    in_tok = obj.get("input_tokens") or obj.get("prompt_tokens") or 0
    out_tok = obj.get("output_tokens") or obj.get("completion_tokens") or 0
    try:
        in_tok = int(in_tok)
        out_tok = int(out_tok)
    except (TypeError, ValueError):
        return None
    if in_tok == 0 and out_tok == 0:
        return None
    return StageTokens(
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_cents=estimate_cost_cents(model, in_tok, out_tok),
    )


def parse_llm_calls_file(path: Path) -> list[StageTokens]:
    """Parse a Plato ``LLM_calls.txt`` file. Malformed lines are skipped."""
    if not path.exists() or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[StageTokens] = []
    is_json = text.lstrip().startswith("{")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rec = _parse_json_line(line) if is_json else _parse_kv_line(line)
        if rec is not None:
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _stage_log_path(project_dir: Path, stage: str) -> Path:
    dir_stage = _STAGE_DIR_OVERRIDES.get(stage, stage)
    return project_dir / f"{dir_stage}_generation_output" / "LLM_calls.txt"


def aggregate_project_usage(project_dir: Path) -> ProjectUsage:
    """Aggregate token usage + cost across all stages of a project."""
    usage = ProjectUsage()
    for stage in _STAGES:
        path = _stage_log_path(project_dir, stage)
        records = parse_llm_calls_file(path)
        if not records:
            continue
        stage_total = StageTokens()
        for rec in records:
            stage_total.add(rec)
            canonical = normalize_model_id(rec.model) or (rec.model or "unknown")
            slot = usage.by_model.setdefault(canonical, StageTokens(model=canonical))
            slot.input_tokens += rec.input_tokens
            slot.output_tokens += rec.output_tokens
            slot.cost_cents += rec.cost_cents
        usage.by_stage[stage] = stage_total
        usage.total_input += stage_total.input_tokens
        usage.total_output += stage_total.output_tokens
        usage.total_cost_cents += stage_total.cost_cents
    return usage


# ---------------------------------------------------------------------------
# Live in-memory ledger (driven by EventBus 'tokens.delta' events)
# ---------------------------------------------------------------------------

_run_ledger: dict[str, StageTokens] = {}
_ledger_lock = threading.Lock()


def record_tokens_delta(
    run_id: str,
    model: Optional[str],
    prompt_tok: int,
    completion_tok: int,
) -> StageTokens:
    """Accumulate a token delta into the live ledger for ``run_id``."""
    prompt_tok = max(int(prompt_tok or 0), 0)
    completion_tok = max(int(completion_tok or 0), 0)
    with _ledger_lock:
        slot = _run_ledger.get(run_id)
        if slot is None:
            slot = StageTokens(model=model)
            _run_ledger[run_id] = slot
        if model and not slot.model:
            slot.model = model
        slot.input_tokens += prompt_tok
        slot.output_tokens += completion_tok
        slot.cost_cents += estimate_cost_cents(slot.model, prompt_tok, completion_tok)
        return StageTokens(
            model=slot.model,
            input_tokens=slot.input_tokens,
            output_tokens=slot.output_tokens,
            cost_cents=slot.cost_cents,
        )


def get_run_usage(run_id: str) -> StageTokens:
    """Return a snapshot of the live ledger entry for ``run_id``."""
    with _ledger_lock:
        slot = _run_ledger.get(run_id)
        if slot is None:
            return StageTokens()
        return StageTokens(
            model=slot.model,
            input_tokens=slot.input_tokens,
            output_tokens=slot.output_tokens,
            cost_cents=slot.cost_cents,
        )


def reconcile_run(
    run_id: str,
    project_dir: Path,
    stage: str,
) -> StageTokens:
    """When a run finishes, replace the ledger entry with canonical totals
    parsed from the on-disk LLM_calls.txt for ``stage``. The on-disk file
    is the source of truth.
    """
    records = parse_llm_calls_file(_stage_log_path(project_dir, stage))
    canonical = StageTokens()
    for rec in records:
        canonical.add(rec)
    with _ledger_lock:
        _run_ledger[run_id] = canonical
    return StageTokens(
        model=canonical.model,
        input_tokens=canonical.input_tokens,
        output_tokens=canonical.output_tokens,
        cost_cents=canonical.cost_cents,
    )


def clear_run_ledger() -> None:
    """Test helper — drops all in-memory entries."""
    with _ledger_lock:
        _run_ledger.clear()


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def _smoke_test() -> None:
    import tempfile

    sample = [
        # gpt-5: 4000 input + 1000 output → $0.10 = 10 cents
        "2026-04-29T08:08:12 input_tokens=4000 output_tokens=1000 model=gpt-5",
        # gpt-4.1-mini: 2000 input + 500 output → $0.0008 + $0.0008 = $0.0016 = 0 cents
        "2026-04-29T08:09:00 input_tokens=2000 output_tokens=500 model=gpt-4.1-mini",
        # claude-4.1-opus: 1000 + 500 → $0.015 + $0.0375 = $0.0525 = 5 cents
        "2026-04-29T08:10:00 input_tokens=1000 output_tokens=500 model=claude-4.1-opus",
        # malformed line — should be skipped
        "garbage line with no key=value",
        # dated anthropic id — should normalize to claude-4.1-opus
        "2026-04-29T08:11:00 input_tokens=200 output_tokens=100 model=claude-opus-4-1-20250805",
    ]

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "prj_demo"
        idea_dir = proj / "idea_generation_output"
        idea_dir.mkdir(parents=True)
        (idea_dir / "LLM_calls.txt").write_text("\n".join(sample) + "\n")

        usage = aggregate_project_usage(proj)
        print("--- aggregate_project_usage ---")
        print(f"total_input  = {usage.total_input}")
        print(f"total_output = {usage.total_output}")
        print(f"total_cost   = {usage.total_cost_cents} cents")
        print(f"by_stage     = {usage.by_stage}")
        print(f"by_model     = {usage.by_model}")

        # gpt-5 alone: 4000*0.0125/1000 + 1000*0.050/1000 = 0.05 + 0.05 = $0.10 = 10 cents
        gpt5_cents = estimate_cost_cents("gpt-5", 4000, 1000)
        print(f"\nestimate_cost_cents('gpt-5', 4000, 1000) = {gpt5_cents}  (expect 10)")
        assert gpt5_cents == 10, f"gpt-5 cost arithmetic broken: {gpt5_cents}"

        # Normalization checks
        cases = {
            "claude-opus-4-1-20250805": "claude-4.1-opus",
            "gpt-5-2025-08-07": "gpt-5",
            "GPT-5": "gpt-5",
            "claude-3-7-sonnet-20240219": "claude-3.7-sonnet",
            "gemini-2.5-pro": "gemini-2.5-pro",
            "unknown-model-xyz": "unknown-model-xyz",
            "": None,
        }
        print("\n--- normalize_model_id ---")
        for raw, want in cases.items():
            got = normalize_model_id(raw)
            ok = "OK " if got == want else "BAD"
            print(f"  [{ok}] {raw!r:40s} -> {got!r}  (want {want!r})")
            assert got == want, (raw, got, want)

        # Live ledger round-trip
        clear_run_ledger()
        record_tokens_delta("run_x", "gpt-5", 1000, 200)
        record_tokens_delta("run_x", "gpt-5", 3000, 800)
        snap = get_run_usage("run_x")
        print(
            f"\nlive ledger run_x: in={snap.input_tokens} out={snap.output_tokens} "
            f"cost={snap.cost_cents}c (expect in=4000 out=1000 cost=10)"
        )
        assert (snap.input_tokens, snap.output_tokens, snap.cost_cents) == (4000, 1000, 10)

        # Reconciliation: prefer canonical on-disk totals.
        reconciled = reconcile_run("run_x", proj, "idea")
        print(
            f"reconciled run_x: in={reconciled.input_tokens} out={reconciled.output_tokens} "
            f"cost={reconciled.cost_cents}c"
        )
        assert reconciled.input_tokens == usage.total_input

    print("\nAll token_tracker smoke checks passed.")


if __name__ == "__main__":
    _smoke_test()
