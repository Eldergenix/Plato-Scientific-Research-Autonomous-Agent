"""Unit tests for the library tools wired into the live scientist (no database needed)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from plato.retrieval.reranker import bm25_rank
from plato.scientist.citations import check_sources, exclusion_reason
from plato.scientist.executors import run_experiment
from plato.scientist.guard.modal_runner import run_python_modal
from plato.scientist.nodes import ScientistConfig, code_rules
from plato.scientist.profiles import classify, get_profile, resolve_profile
from plato.scientist.review import (
    build_evidence_matrix,
    extract_cited_claims,
    matrix_required_changes,
    quote_span,
    run_review_panel,
)
from plato.scientist.schemas import (
    CitationSupport,
    EvidenceMatrix,
    Manuscript,
    PanelCritique,
)
from plato.state.models import Source


def _src(**kw) -> Source:
    base = {
        "id": uuid.uuid4().hex,
        "title": "A paper",
        "retrieved_via": "openalex",
        "fetched_at": datetime.now(UTC),
    }
    return Source(**{**base, **kw})


# --- profiles ---------------------------------------------------------------


@pytest.mark.parametrize(
    "label,expected",
    [
        ("general", None),
        ("statistics", "general"),
        ("standard errors", "general"),  # "star" must not match
        ("generalization", "general"),  # "gene" must not match
        ("journal analysis", "general"),  # "rna" must not match
        ("computational_biology", "biology"),
        ("single-cell RNA-seq", "biology"),
        ("epidemiology", "biology"),
        ("astrophysics", "astro"),
        ("exoplanet transits", "astro"),
    ],
)
def test_domain_labels_map_to_profiles(label, expected):
    assert classify(label) == expected


def test_specific_plan_domain_refines_unspecific_request():
    assert resolve_profile("general", None, "computational_biology").name == "biology"
    assert resolve_profile("astronomy", None, "computational_biology").name == "astro"
    assert resolve_profile("statistics", "general", "ml").name == "general"


def test_profiles_use_library_source_lists_and_packages():
    bio, astro, gen = (
        get_profile("biology"),
        get_profile("astro"),
        get_profile("general"),
    )
    assert {"pubmed", "europe_pmc"} <= set(bio.retrieval_sources)
    assert "ads" in astro.retrieval_sources
    assert {"arxiv", "openalex", "semantic_scholar", "crossref"} <= set(
        gen.retrieval_sources
    )
    assert "biopython" in bio.packages and "astropy" in astro.packages
    assert "statsmodels" in gen.packages


def test_code_rules_follow_profile_and_executor():
    cfg = ScientistConfig.from_campaign({"executor": "modal", "gpu": "T4"})
    assert cfg.sandbox.wall_seconds == 600
    rules = code_rules(get_profile("biology"), cfg)
    assert (
        "biopython" in rules
        and "torch is installed" in rules
        and "600 seconds" in rules
    )
    assert "torch" not in code_rules(get_profile("general"), ScientistConfig())


# --- ranking ------------------------------------------------------------------


def test_bm25_ranks_relevant_paper_first_regardless_of_adapter_order():
    noise = [
        _src(title=f"Unrelated topic {i}", abstract="galaxy rotation") for i in range(5)
    ]
    hit = _src(
        title="Bootstrap confidence intervals",
        abstract="coverage of bootstrap intervals",
    )
    ranked = bm25_rank("bootstrap interval coverage", [*noise, hit], top_k=2)
    assert ranked[0] is hit and len(ranked) == 2


# --- citation checks -----------------------------------------------------------


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_check_sources_flags_retraction_and_resolves_datacite_doi():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://api.crossref.org/works/10.1000/retracted"):
            return httpx.Response(
                200,
                json={
                    "message": {
                        "DOI": "10.1000/retracted",
                        "title": ["A paper"],
                        "updated-by": [{"type": "retraction", "DOI": "10.1000/notice"}],
                    }
                },
            )
        if url.startswith("https://api.crossref.org/works/10.5281"):
            return httpx.Response(404)
        if url.startswith("https://doi.org/api/handles/10.5281"):
            return httpx.Response(200, json={"responseCode": 1})
        return httpx.Response(404)

    async with _client(handler) as client:
        checks = await check_sources(
            [_src(doi="10.1000/retracted"), _src(doi="10.5281/zenodo.42")],
            http_client=client,
        )
    assert checks[0]["retracted"] is True
    assert exclusion_reason(checks[0]) == "retracted"
    assert checks[1]["doi_resolved"] is True and exclusion_reason(checks[1]) is None


async def test_check_sources_never_raises_on_outage():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with _client(handler) as client:
        checks = await check_sources([_src(doi="10.1000/x")], http_client=client)
    assert exclusion_reason(checks[0]) is None  # an outage never removes literature


def test_wrong_work_identifier_is_excluded():
    assert "different work" in exclusion_reason(
        {"status": "error", "issues": ["title_mismatch"]}
    )
    assert (
        exclusion_reason({"status": "error", "issues": ["url_verification_failed"]})
        is None
    )


# --- claim-evidence matrix and reviewer panel --------------------------------------


MS = Manuscript(
    title="T",
    abstract="We study coverage.",
    introduction=(
        "Bootstrap intervals under-cover in small samples \\cite{ref_a}. "
        "Robust errors fix heteroskedasticity \\cite{ref_b,ref_fake}. No citation here."
    ),
    methods="m",
    results="r",
    discussion="d",
    limitations="l",
)
PAPERS = {
    "ref_a": {
        "canonical_name": "Paper A",
        "metadata": {
            "abstract": "We show that bootstrap  intervals\nunder-cover when n is small."
        },
    },
    "ref_b": {
        "canonical_name": "Paper B",
        "metadata": {"abstract": "A study of galaxies."},
    },
}


def test_cited_sentences_become_claims_with_allowed_keys_only():
    claims = extract_cited_claims(MS, set(PAPERS))
    assert [c["keys"] for c in claims] == [["ref_a"], ["ref_b"]]
    assert "\\cite" not in claims[0]["text"]


def test_quote_span_is_whitespace_and_case_insensitive():
    abstract = PAPERS["ref_a"]["metadata"]["abstract"]
    span = quote_span(abstract, "Bootstrap intervals under-cover when n is small")
    assert span is not None and abstract[span[0] : span[1]].startswith("bootstrap")
    assert quote_span(abstract, "bootstrap intervals over-cover") is None


class _Model:
    def __init__(self, links):
        self.links, self.calls = links, []

    async def structured(self, *, purpose, schema, prompt, **_):
        self.calls.append(purpose)
        if schema is EvidenceMatrix:
            return EvidenceMatrix(links=self.links)
        if schema is PanelCritique:
            if purpose == "review_writing":
                raise RuntimeError("boom")
            return PanelCritique(severity=7, summary="s", issues=[])
        raise AssertionError(schema)


async def test_unquotable_support_is_downgraded_and_triggers_revision():
    model = _Model(
        [
            CitationSupport(
                pair_index=0,
                support="supports",
                strength="strong",
                quote="bootstrap intervals under-cover when n is small",
                rationale="r",
            ),
            # Claims support but quotes text that is not in Paper B's abstract.
            CitationSupport(
                pair_index=1,
                support="supports",
                strength="strong",
                quote="robust errors fix heteroskedasticity",
                rationale="r",
            ),
        ]
    )
    matrix = await build_evidence_matrix(model, uuid.uuid4(), MS, PAPERS)
    verdicts = [c["verdict"] for c in matrix["claims"]]
    assert verdicts == ["supported", "unsupported"]
    assert matrix["unsupported_claim_rate"] == 0.5
    changes = matrix_required_changes(matrix)
    assert len(changes) == 1 and "ref_b" in changes[0]
    json.dumps(matrix)  # stored as a JSON receipt


async def test_panel_runs_four_reviewers_and_survives_one_failure():
    model = _Model([])
    panel = await run_review_panel(model, uuid.uuid4(), MS, "evidence")
    assert set(panel["reviewers"]) == {
        "methodology",
        "statistics",
        "novelty",
        "writing",
    }
    assert "error" in panel["reviewers"]["writing"]
    assert panel["completed"] == 3 and panel["max_severity"] == 5  # clamped to 0..5


# --- executors -------------------------------------------------------------------


async def test_modal_runner_refuses_without_credentials(monkeypatch):
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    result = await run_python_modal("print(1)")
    assert result.rejected == "Modal credentials are not configured"
    assert (await run_python_modal("import socket")).rejected  # same static policy
    assert (await run_python_modal("print(1)", gpu="RTX9000")).rejected


async def test_modal_executor_falls_back_to_local_sandbox_without_credentials(
    monkeypatch,
):
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    cfg = ScientistConfig.from_campaign({"executor": "modal"})
    result = await run_experiment(cfg, "print('PLATO_METRICS {\"x\": 1}')", inputs={})
    assert result.ok and "PLATO_METRICS" in result.stdout
