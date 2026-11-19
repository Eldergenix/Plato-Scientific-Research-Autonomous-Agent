"""Unit tests for the library tools wired into the live scientist (no database needed)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from plato.retrieval.reranker import bm25_rank
from plato.scientist.citations import check_sources, exclusion_reason
from plato.scientist.executors import run_experiment
from plato.scientist.guard.modal_runner import run_python_modal
from plato.scientist.nodes import ScientistConfig, code_rules, profile_tools
from plato.scientist.profiles import classify, get_profile, resolve_profile
from plato.scientist.review import (
    apply_revision,
    build_evidence_matrix,
    extract_cited_claims,
    matrix_required_changes,
    quote_span,
    review_record,
    run_review_panel,
)
from plato.scientist.schemas import (
    CitationSupport,
    ClaimAssessment,
    EvidenceMatrix,
    Manuscript,
    PanelCritique,
    PeerReview,
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
        ("chemical compound screening", "biology"),
        ("ligand docking", "biology"),
        ("biochemical pathway analysis", "biology"),
        ("enzyme kinetics", "biology"),
        ("molecular dynamics of a membrane protein", "biology"),
        ("molecular clouds in star-forming regions", "astro"),  # astro wins "molecular"
        ("structural equation modelling", "general"),  # "structure" must not match
        ("compound interest forecasting", "general"),  # "compound" must not match
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


def test_molecular_guidance_reaches_a_live_lab_session_only():
    """The offline executors have a fixed package list, so the lab's molecular tools are
    offered to the planner (and the workspace agent) only when the executor is E2B."""
    bio, gen = get_profile("biology"), get_profile("general")
    assert "SAPT" in bio.workspace_guidance and "FDR" in bio.workspace_guidance
    assert gen.workspace_guidance == ""
    e2b = ScientistConfig.from_campaign({"executor": "e2b"})
    assert "AutoDock Vina" in profile_tools(bio, e2b)
    assert profile_tools(bio, ScientistConfig()) == "/".join(bio.packages)
    # A database annotation is never the result: the rules must say so in both places.
    assert "annotation" in bio.workspace_guidance
    assert "not binding affinities" in bio.workspace_guidance


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
            "abstract": "We show that bootstrap  intervals\nunder-cover when n is small. "
            "Simulations across ten designs confirm it."
        },
    },
    "ref_b": {
        "canonical_name": "Paper B",
        "metadata": {
            "abstract": "A study of galaxies: rotation curves of 120 spirals measured "
            "with radio interferometry."
        },
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


def _assessment(section: str, quote: str, verdict: str = "approved") -> ClaimAssessment:
    return ClaimAssessment(
        section=section,
        quote=quote,
        category="result",
        verdict=verdict,
        severity="minor",
        evidence="e",
        critique="c",
        fix="",
    )


def test_review_record_locates_each_claim_and_counts_verdicts():
    review = PeerReview(
        summary="s",
        strengths=[],
        assessments=[
            # whitespace and case differ, the LaTeX is as written
            _assessment(
                "introduction",
                "bootstrap  intervals under-cover in small samples \\cite{ref_a}.",
            ),
            # moved: quoted under the wrong section, still found in the paper
            _assessment(
                "results", "Robust errors fix heteroskedasticity", "needs_revision"
            ),
            _assessment("abstract", "We prove coverage is exact.", "rejected"),
        ],
        soundness=3,
        presentation=3,
        contribution=2,
        decision="major_revision",
        required_changes=[],
    )
    rec = review_record(review, MS)
    assert [a["id"] for a in rec["assessments"]] == [0, 1, 2]
    assert [a["quote_found"] for a in rec["assessments"]] == [True, True, False]
    assert rec["counts"] == {"approved": 1, "needs_revision": 1, "rejected": 1}
    # Without a revision check, only whether each quote is still in the final text is known.
    final = MS.model_copy(
        update={"introduction": "Robust errors fix heteroskedasticity."}
    )
    out = apply_revision(rec, None, final)
    assert [a["final_quote_found"] for a in out["assessments"]] == [False, True, False]
    assert "revision" not in out and all("outcome" not in a for a in out["assessments"])


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


async def test_citations_to_papers_without_an_abstract_are_unchecked_not_unsupported():
    papers = {
        **PAPERS,
        "ref_b": {"canonical_name": "Paper B", "metadata": {"abstract": ""}},
    }
    model = _Model(
        [
            CitationSupport(
                pair_index=0,
                support="supports",
                strength="strong",
                quote="bootstrap intervals under-cover when n is small",
                rationale="r",
            )
        ]
    )
    matrix = await build_evidence_matrix(model, uuid.uuid4(), MS, papers)
    assert [c["verdict"] for c in matrix["claims"]] == ["supported", "unchecked"]
    # The unchecked claim is not counted against the paper and asks for no change.
    assert matrix["unsupported_claim_rate"] == 0.0 and matrix["unchecked_claims"] == 1
    assert matrix_required_changes(matrix) == []
    # Nothing to judge at all: no model call.
    empty = _Model([])
    only_b = MS.model_copy(update={"introduction": "Robust errors \\cite{ref_b}."})
    out = await build_evidence_matrix(empty, uuid.uuid4(), only_b, papers)
    assert empty.calls == [] and out["claims"][0]["verdict"] == "unchecked"


async def test_unsupported_citations_are_stripped_from_the_final_paper():
    from plato.scientist.review import strip_unsupported_citations

    ms = MS.model_copy(
        update={
            "introduction": (
                "Bootstrap intervals under-cover in small samples \\cite{ref_a}. "
                "Robust errors fix heteroskedasticity \\cite{ref_a,ref_b}. "
                "Robust errors fix heteroskedasticity again \\cite{ref_b}. No citation here."
            )
        }
    )
    links = [
        CitationSupport(
            pair_index=i,
            support="supports" if i == 0 else "unclear",
            strength="strong",
            quote="bootstrap intervals under-cover when n is small" if i == 0 else "",
            rationale="r",
        )
        for i in range(5)
    ]
    matrix = await build_evidence_matrix(_Model(links), uuid.uuid4(), ms, PAPERS)
    assert [c["verdict"] for c in matrix["claims"]] == [
        "supported",
        "unsupported",
        "unsupported",
    ]
    final_ms, final, removed = strip_unsupported_citations(ms, matrix)
    assert final_ms.introduction == (
        "Bootstrap intervals under-cover in small samples \\cite{ref_a}. "
        "Robust errors fix heteroskedasticity. "
        "Robust errors fix heteroskedasticity again. No citation here."
    )
    assert [r["keys"] for r in removed] == [["ref_a", "ref_b"], ["ref_b"]]
    # The stored matrix describes the published paper; the earlier rate is kept.
    assert [c["verdict"] for c in final["claims"]] == ["supported"]
    assert final["unsupported_claim_rate"] == 0.0
    assert final["unsupported_claim_rate_before_removal"] == round(2 / 3, 4)
    # Idempotent on a paper with nothing left to remove.
    again, same, none = strip_unsupported_citations(final_ms, final)
    assert again == final_ms and none == [] and same is final


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


# --- merged ranking -----------------------------------------------------------------


def test_supplementary_files_are_recognised_but_real_titles_are_not():
    from plato.retrieval.orchestrator import is_supplementary

    for title in (
        "Additional file 5: of Three-dimensional printed PLA scaffold",
        "Supplemental material for: [Maternal Estradiol Impacts Fetal HPA Axis]",
        "Supplementary Information for Temporal changes in macrophages",
        "Figure S2 from CD8+ T cells maintain killing",
        "Table 3 of Gene expression in liver",
        "Source data for Supplementary Data 12: Annotation of Humulus genes",
    ):
        assert is_supplementary(_src(title=title)), title
    for title in (
        "Supplemental oxygen therapy in acute myocardial infarction",
        "Supplementary vitamin D and fracture risk",
        "False discovery rate control: moving beyond Benjamini-Hochberg",
    ):
        assert not is_supplementary(_src(title=title)), title


def test_dedup_merges_versioned_dois_with_the_same_title_and_year():
    from plato.retrieval.dedup import dedup_sources

    a = _src(
        doi="10.6084/m9.figshare.1",
        title="CD8+ T cells maintain killing of MHC-I-negative tumor cells",
        year=2024,
    )
    b = _src(
        doi="10.6084/m9.figshare.1.v1",
        title="CD8+ T cells maintain killing of MHC-I-negative tumor cells",
        year=2024,
        abstract="x",
    )
    other_year = _src(
        doi="10.1/z",
        title="CD8+ T cells maintain killing of MHC-I-negative tumor cells",
        year=2019,
    )
    generic = [
        _src(doi="10.1/e1", title="Editorial"),
        _src(doi="10.1/e2", title="Editorial"),
    ]
    out = dedup_sources([a, b, other_year, *generic])
    assert len(out) == 4 and out[0].abstract == "x"  # merged pair keeps the abstract


async def test_fused_retrieval_keeps_every_relevant_source_in_the_top_slots(
    monkeypatch,
):
    """Regression for a live run where 7 of 8 merged slots went to DataCite records."""
    from plato import retrieval
    from plato.retrieval.orchestrator import retrieve

    q = "Benjamini-Hochberg false discovery rate gene expression"
    stuffed = "gene expression false discovery rate Benjamini Hochberg " * 8

    def adapter(name, titles, abstract=""):
        class A:
            async def search(self, query, limit):
                return [
                    _src(
                        doi=f"10.1/{name}{i}",
                        title=t,
                        abstract=abstract,
                        retrieved_via=name,
                    )
                    for i, t in enumerate(titles)
                ]

        A.name = name
        return A()

    adapters = {
        "pubmed": adapter(
            "pubmed",
            [f"Transcriptomic alterations in cohort {i}" for i in range(8)],
            "we used FDR",
        ),
        "openalex": adapter(
            "openalex",
            ["On the operating characteristics of the Benjamini and Hochberg procedure"]
            + [f"FDR paper {i}" for i in range(7)],
        ),
        "datacite": adapter(
            "datacite",
            [
                f"Gene expression dataset number {i} for false discovery analysis"
                for i in range(8)
            ]
            + ["Additional file 6: of Temporal changes in macrophage phenotype"],
            stuffed,
        ),
    }
    monkeypatch.setattr(retrieval.orchestrator, "get_adapter", lambda n: adapters[n])
    out = await retrieve(
        q,
        8,
        adapter_names=list(adapters),
        rerank_fallback="fused",
        drop_supplementary=True,
    )
    via = [s.retrieved_via for s in out]
    assert len(out) == 8 and set(via) == {"pubmed", "openalex", "datacite"}
    assert max(via.count(v) for v in set(via)) <= 4  # no adapter takes more than half
    assert not any(s.title.startswith("Additional file") for s in out)


async def test_literature_datacite_keeps_only_papers_and_profiles_use_it():
    from plato.retrieval import get_adapter

    def rec(doi, kind):
        return {
            "id": doi,
            "attributes": {
                "doi": doi,
                "titles": [{"title": f"Record {doi}"}],
                "types": {"resourceTypeGeneral": kind},
            },
        }

    payload = {
        "data": [
            rec("10.5061/a", "Dataset"),
            rec("10.5061/b", "JournalArticle"),
            rec("10.5061/c", "Software"),
            rec("10.5061/d", "Preprint"),
            rec("10.5061/e", "Text"),
        ]
    }
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["size"] = request.url.params["page[size]"]
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient.__init__

    def patched(self, *a, **kw):
        kw["transport"] = transport
        real(self, *a, **kw)

    import unittest.mock as um

    with um.patch.object(httpx.AsyncClient, "__init__", patched):
        papers = await get_adapter("datacite_literature").search("q", 2)
        everything = await get_adapter("datacite").search("q", 5)
    assert [p.doi for p in papers] == ["10.5061/b", "10.5061/d"]  # limit 2, papers only
    assert seen["size"] == "5" and len(everything) == 5
    assert all(p.retrieved_via == "datacite" for p in papers)
    bio = get_profile("biology").retrieval_sources
    assert "datacite_literature" in bio and "datacite" not in bio


async def test_missing_abstracts_are_fetched_from_openalex_then_arxiv():
    import httpx

    from plato.scientist.citations import fetch_missing_abstracts

    long = "Bootstrap confidence intervals under-cover in small samples, as ten simulations show."
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "api.openalex.org":
            assert request.url.params["filter"] == "doi:10.1/a|10.1/b"
            words = (long + " Extra words.").split()
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "doi": "https://doi.org/10.1/a",
                            "abstract_inverted_index": {
                                w: [i] for i, w in enumerate(words)
                            },
                        }
                    ]
                },
            )
        assert request.url.params["id_list"] == "2504.08066"
        atom = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<id>http://arxiv.org/abs/2504.08066v2</id>"
            f"<summary>  {long}\n  </summary></entry></feed>"
        )
        return httpx.Response(200, text=atom)

    def src(**kw):
        return SimpleNamespace(**{"doi": None, "arxiv_id": None, **kw})

    sources = [
        src(doi="10.1/a", abstract=""),
        src(doi="https://doi.org/10.1/B", arxiv_id="2504.08066v2", abstract=None),
        src(doi="10.1/c", abstract=long),  # already has one: not looked up
        src(abstract=""),  # nothing to look up by
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out = await fetch_missing_abstracts(sources, http_client=client)
    assert out[0].startswith("Bootstrap confidence") and out[1] == long
    assert out[2] is None and out[3] is None
    assert seen == ["api.openalex.org", "export.arxiv.org"]

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        assert await fetch_missing_abstracts(sources, http_client=client) == [None] * 4
