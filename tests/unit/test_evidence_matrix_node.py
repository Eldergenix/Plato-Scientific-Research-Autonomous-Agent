"""Phase 2 — R5 (LINKER): tests for evidence_matrix_node.

The node is exercised end-to-end with a mocked ``LLM_call`` so the suite
never reaches a chat model. We verify:
- For each drafted-claim × source-claim pair, an EvidenceLink is emitted
  with the support/strength labels parsed from the LLM JSON.
- ``unsupported_claim_rate`` is the fraction of drafted claims with zero
  ``supports`` links.
- ``evidence_matrix.jsonl`` is written one record per line.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from plato.paper_agents import evidence_matrix_node as node_module
from plato.state.models import Claim, EvidenceLink, Source


def _state(tmp_path: Path, drafted, source_claims, sources=None) -> dict:
    return {
        "files": {"Folder": str(tmp_path)},
        "claims": list(drafted) + list(source_claims),
        "sources": list(sources or []),
        "run_id": "run-evi-001",
    }


def _drafted_claim(idx: int, text: str) -> Claim:
    return Claim(id=f"d-{idx:03d}", text=text, source_id=None, section="abstract")


def _source_claim(idx: int, text: str, source_id: str = "src-1") -> Claim:
    return Claim(id=f"s-{idx:03d}", text=text, source_id=source_id, section="abstract")


def _llm_returning(payloads):
    """Yield each payload as ```json fenced block, in order."""
    iterator = iter(payloads)

    def _side_effect(prompt, state, *, node_name=None):
        try:
            payload = next(iterator)
        except StopIteration as exc:
            raise AssertionError("LLM_call invoked more times than scripted") from exc
        body = json.dumps(payload) if isinstance(payload, dict) else payload
        return state, f"```json\n{body}\n```"

    return _side_effect


def test_two_drafted_claims_one_source_claim_produces_two_links(tmp_path):
    drafted = [
        _drafted_claim(0, "Dark matter is 27% of the universe."),
        _drafted_claim(1, "Galaxies form via hierarchical merging."),
    ]
    source_claims = [
        _source_claim(0, "Observations confirm dark matter at 27%.", "src-1"),
    ]
    state = _state(tmp_path, drafted, source_claims, sources=[
        Source(
            id="src-1", title="Stub", retrieved_via="arxiv",
            fetched_at=datetime.now(timezone.utc),
        ),
    ])

    payloads = [
        {"support": "supports", "strength": "strong", "rationale": "matches"},
        {"support": "neutral", "strength": "weak", "rationale": "off-topic"},
    ]
    with patch.object(node_module, "LLM_call", side_effect=_llm_returning(payloads)):
        update = node_module.evidence_matrix_node(state)

    links = update["evidence_links"]
    assert len(links) == 2
    assert all(isinstance(l, EvidenceLink) for l in links)

    by_claim = {l.claim_id: l for l in links}
    assert by_claim["d-000"].support == "supports"
    assert by_claim["d-000"].strength == "strong"
    assert by_claim["d-000"].source_id == "src-1"
    assert by_claim["d-001"].support == "neutral"


def test_jsonl_file_written_one_record_per_line(tmp_path):
    drafted = [_drafted_claim(0, "Claim A")]
    source_claims = [
        _source_claim(0, "Source claim 1", "src-1"),
        _source_claim(1, "Source claim 2", "src-2"),
    ]
    state = _state(tmp_path, drafted, source_claims)

    payloads = [
        {"support": "supports", "strength": "moderate", "rationale": "."},
        {"support": "refutes", "strength": "weak", "rationale": "."},
    ]
    with patch.object(node_module, "LLM_call", side_effect=_llm_returning(payloads)):
        update = node_module.evidence_matrix_node(state)

    jsonl_path = tmp_path / "runs" / "run-evi-001" / "evidence_matrix.jsonl"
    assert jsonl_path.exists()

    lines = jsonl_path.read_text().strip().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    supports = sorted(p["support"] for p in parsed)
    assert supports == ["refutes", "supports"]


def test_unsupported_claim_rate_one_supported_one_not(tmp_path):
    drafted = [
        _drafted_claim(0, "Supported claim"),
        _drafted_claim(1, "Unsupported claim"),
    ]
    source_claims = [_source_claim(0, "Some source claim", "src-1")]
    state = _state(tmp_path, drafted, source_claims)

    payloads = [
        {"support": "supports", "strength": "strong", "rationale": "."},
        {"support": "refutes", "strength": "weak", "rationale": "."},
    ]
    with patch.object(node_module, "LLM_call", side_effect=_llm_returning(payloads)):
        update = node_module.evidence_matrix_node(state)

    # 1 of 2 drafted claims has a "supports" link → unsupported_rate = 0.5
    assert update["unsupported_claim_rate"] == 0.5


def test_no_drafted_claims_yields_zero_rate(tmp_path):
    state = _state(tmp_path, [], [])
    with patch.object(node_module, "LLM_call") as mocked:
        update = node_module.evidence_matrix_node(state)
    mocked.assert_not_called()
    assert update["unsupported_claim_rate"] == 0.0
    assert update["evidence_links"] == []


def test_no_source_claims_or_sources_marks_all_unsupported(tmp_path):
    """When the corpus is empty, every drafted claim is unsupported."""
    drafted = [_drafted_claim(0, "Lonely claim")]
    state = _state(tmp_path, drafted, [], sources=[])

    with patch.object(node_module, "LLM_call") as mocked:
        update = node_module.evidence_matrix_node(state)

    mocked.assert_not_called()
    assert update["unsupported_claim_rate"] == 1.0
    # An empty matrix file is still written for reproducibility.
    assert (tmp_path / "runs" / "run-evi-001" / "evidence_matrix.jsonl").exists()


def test_unclear_classification_skips_link(tmp_path):
    """A 'unclear' verdict carries no signal and must NOT produce a link."""
    drafted = [_drafted_claim(0, "Ambiguous claim")]
    source_claims = [_source_claim(0, "Ambiguous source", "src-1")]
    state = _state(tmp_path, drafted, source_claims)

    payloads = [{"support": "unclear", "strength": "weak", "rationale": "."}]
    with patch.object(node_module, "LLM_call", side_effect=_llm_returning(payloads)):
        update = node_module.evidence_matrix_node(state)

    assert update["evidence_links"] == []
    assert update["unsupported_claim_rate"] == 1.0


def test_existing_evidence_links_preserved(tmp_path):
    """Pre-existing evidence links must survive; new links are appended."""
    drafted = [_drafted_claim(0, "Drafted")]
    source_claims = [_source_claim(0, "Source", "src-1")]
    state = _state(tmp_path, drafted, source_claims)
    state["evidence_links"] = [
        EvidenceLink(claim_id="prev-1", source_id="src-old", support="supports", strength="strong"),
    ]

    payloads = [{"support": "supports", "strength": "moderate", "rationale": "."}]
    with patch.object(node_module, "LLM_call", side_effect=_llm_returning(payloads)):
        update = node_module.evidence_matrix_node(state)

    links = update["evidence_links"]
    assert len(links) == 2
    assert links[0].claim_id == "prev-1"
    assert links[1].claim_id == "d-000"


def test_malformed_llm_response_retries_then_skips(tmp_path):
    """3 malformed JSON responses → no link emitted, no crash."""
    drafted = [_drafted_claim(0, "Claim")]
    source_claims = [_source_claim(0, "Source", "src-1")]
    state = _state(tmp_path, drafted, source_claims)

    bad_payloads = ["not json", "still not json", "really not json"]

    def _bad_side_effect(prompt, state, *, node_name=None):
        return state, bad_payloads.pop(0) if bad_payloads else "no json"

    with patch.object(node_module, "LLM_call", side_effect=_bad_side_effect):
        update = node_module.evidence_matrix_node(state)

    assert update["evidence_links"] == []
    assert update["unsupported_claim_rate"] == 1.0


def test_persists_to_store_when_present(tmp_path):
    """A wired Store should receive every EvidenceLink that's actually emitted."""
    from unittest.mock import MagicMock

    drafted = [_drafted_claim(0, "Claim")]
    source_claims = [_source_claim(0, "Source", "src-1")]
    state = _state(tmp_path, drafted, source_claims)
    fake_store = MagicMock()
    state["store"] = fake_store

    payloads = [{"support": "supports", "strength": "strong", "rationale": "."}]
    with patch.object(node_module, "LLM_call", side_effect=_llm_returning(payloads)):
        node_module.evidence_matrix_node(state)

    assert fake_store.add_evidence.call_count == 1
