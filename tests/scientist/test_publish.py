"""Publication packages: a real campaign (fake model, real Postgres, real sandbox) is
exported for every journal profile with real pdfLaTeX and pandoc."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import shutil
import zipfile
from asyncio.subprocess import PIPE

import pytest
from test_end_to_end import FakeModel, _new_campaign, fake_retriever

from plato.publish import journals
from plato.publish.adapt import (
    AbstractSection,
    JournalAdaptation,
    KeyPoints,
    ResearchInContext,
    grant_budget,
    unsupported_numbers,
)
from plato.publish.collect import NotPublishable, collect, parse_manuscript
from plato.publish.package import PreviewFailed, build_package, preview_pdf
from plato.publish.texsafe import lancet_decimals, sanitize, strip_citations
from plato.scientist.db.store import BudgetExceeded
from plato.scientist.graph import run_campaign
from plato.scientist.nodes import ScientistContext

needs_tex = pytest.mark.skipif(
    not (shutil.which("pdflatex") and shutil.which("pandoc")),
    reason="pdflatex and pandoc are required",
)


class PublishModel(FakeModel):
    """FakeModel that also writes journal front matter."""

    model = "fake-model"

    async def structured(self, *, campaign_id, purpose, system, prompt, schema, **kw):
        if schema is not JournalAdaptation:
            return await super().structured(
                campaign_id=campaign_id,
                purpose=purpose,
                system=system,
                prompt=prompt,
                schema=schema,
                **kw,
            )
        await self.store.reserve_tokens(campaign_id, self.per_call, keep_free=0)
        self.calls.append(purpose)
        self.prompts[purpose] = prompt
        assert "untrusted" in system
        headings = [
            line.split(":", 1)[1].split(";")
            for line in prompt.splitlines()
            if line.startswith("- abstract: structured")
        ]
        if headings:
            names = [
                h.strip()
                .removeprefix("with exactly these headings in this order")
                .strip(" :.")
                for h in headings[0]
            ]
            names = [
                n.split(" at most")[0].strip(" .")
                for n in names
                if n and not n.strip().startswith("at most")
            ]
            abstract = [
                AbstractSection(heading=n, text=f"{n} text with mean 3.0.")
                for n in names
            ]
        else:
            abstract = [
                AbstractSection(
                    heading="Abstract", text="We measure y; its mean is 3.0 \\cite{x}."
                )
            ]
        n_fig = sum(
            1
            for line in prompt.split("Figures:\n", 1)[1].split("\n\n")[0].splitlines()
            if line.startswith("[")
        )
        return JournalAdaptation(
            title="The mean of y exceeds 2",
            abstract=abstract,
            conclusions="The mean of y exceeds 2 (mean 3.0).",
            key_points=KeyPoints(
                question="Is the mean of y above 2?",
                findings="Mean 3.0.",
                meaning="Yes.",
            ),
            highlights=[
                "Mean of y is 3.0",
                "Bootstrap supports it",
                "Computational study",
            ],
            etoc_blurb="Plato measures y.",
            research_in_context=ResearchInContext(
                evidence_before="Little.",
                added_value="A measurement.",
                implications="Few.",
            ),
            keywords=["bootstrap", "mean", "estimation"],
            figure_titles=[f"Figure title {i + 1}" for i in range(n_fig)]
            + ["Invented 99.9% figure"],
        )


async def _completed(store):
    _, cid, _, _ = await _new_campaign(store)
    model = PublishModel(store)
    ctx = ScientistContext(store=store, model=model, retriever=fake_retriever)
    summary = await run_campaign(ctx, cid)
    assert summary["campaign"]["status"] == "completed"
    return cid, model


@needs_tex
async def test_every_journal_builds_a_complete_package(store):
    cid, model = await _completed(store)
    m = await collect(store, cid)
    assert m.title == "Mean of y" and m.sections["results"] == "mean_y = 3.0"
    for key in journals.JOURNALS:
        pkg = await build_package(store, model, cid, key, crossref=False)
        with zipfile.ZipFile(io.BytesIO(pkg.zip_bytes)) as z:
            names = set(z.namelist())
            top = pkg.name
            for f in (
                "manuscript/manuscript.pdf",
                "manuscript/manuscript.tex",
                "manuscript/manuscript.docx",
                "manuscript/manuscript.jats.xml",
                "manuscript/references.bib",
                "supplement/supplementary_information.pdf",
                "data/data_S1.xlsx",
                "data/findings.csv",
                "data/experiments.csv",
                "data/metrics.json",
                "data/input/train.csv",
                "README.md",
                "SUBMISSION_CHECKLIST.md",
                "PROVENANCE.json",
                "MANIFEST.json",
                "CITATION.cff",
            ):
                assert f"{top}/{f}" in names, (key, f)
            assert not any("holdout" in n for n in names), (
                "sealed data must never be exported"
            )
            assert any(n.startswith(f"{top}/code/") for n in names)
            assert any(n.startswith(f"{top}/manuscript/figures/") for n in names)
            tex = z.read(f"{top}/manuscript/manuscript.tex").decode()
            manifest = json.loads(z.read(f"{top}/MANIFEST.json"))
            assert "manuscript/manuscript.pdf" in manifest["files"]
            assert z.read(f"{top}/manuscript/manuscript.pdf").startswith(b"%PDF")
            jats = z.read(f"{top}/manuscript/manuscript.jats.xml").decode()
            assert "<article" in jats and "ref-list" in jats
            docx = zipfile.ZipFile(
                io.BytesIO(z.read(f"{top}/manuscript/manuscript.docx"))
            )
            doc_xml = docx.read("word/document.xml").decode()
            text = re.sub(r"<[^>]+>", "", doc_xml)
            assert "bootstrap methods revisited" in text.lower(), (
                key,
                text[-1500:],
            )  # citeproc reference list
            if key == "arxiv":
                assert (
                    f"{top}/arxiv/main.tex" in names
                    and f"{top}/arxiv/anc/data/findings.csv" in names
                )
        j = journals.get(key)
        assert pkg.pdf_ok, key
        assert "\\begin{thebibliography}" in tex
        assert "bootstrap methods revisited" in tex.lower()
        assert ("\\linenumbers" in tex) == j.line_numbers
        assert ("\\doublespacing" in tex) == j.double_spaced
        if j.abstract.headings:
            for h in j.abstract.headings:
                assert f"\\textbf{{{h}:}}" in tex, (key, h)
        if j.key_points:
            assert "Key Points" in tex
        if j.research_in_context:
            assert "Research in context" in tex
        if j.highlights:
            assert "Highlights" in tex
        if not j.abstract.citations_allowed:
            after = (
                tex.split("\\section*{" + j.abstract.label)[1].split("}", 1)[1].strip()
            )
            abstract = "\n\n".join(
                after.split("\n\n")[: max(len(j.abstract.headings), 1)]
            )
            assert abstract and "\\cite" not in abstract, (key, abstract)
        checks = {c.id: c for c in pkg.checks}
        assert checks["pdf"].status == "pass"
        assert checks["authors"].status == "fail"  # authors are always the humans' job
        assert checks["numbers"].status == "pass"
        if j.decimal_midpoint:
            assert "\\textperiodcentered" in tex
    # Front matter is written once per journal and cached.
    assert model.calls.count("publication_format") == len(journals.JOURNALS)
    again = await build_package(store, model, cid, "nature", crossref=False)
    assert again.adaptation_source == "model (cached)"
    assert model.calls.count("publication_format") == len(journals.JOURNALS)
    first = await build_package(store, model, cid, "nature", crossref=False)
    assert first.sha256 == again.sha256, "packages must be byte-for-byte reproducible"


@needs_tex
async def test_without_a_model_the_package_still_builds_and_says_so(store):
    cid, _ = await _completed(store)
    pkg = await build_package(
        store, None, cid, "nejm", crossref=False, model_name="test"
    )
    checks = {c.id: c for c in pkg.checks}
    assert pkg.adaptation_source.startswith("fallback")
    assert checks["front_matter"].status == "warn"
    assert checks["abstract_structure"].status == "fail"  # NEJM needs four headings


@needs_tex
async def test_preview_pdf_compiles_without_a_model(store, monkeypatch):
    cid, model = await _completed(store)
    calls = len(model.calls)
    pdf, pages = await preview_pdf(store, cid, model_name="test")
    assert pdf.startswith(b"%PDF-") and pages and pages >= 1
    # The title PDF viewers show (pdfinfo, as the Info dictionary is compressed).
    if shutil.which("pdfinfo"):
        proc = await asyncio.create_subprocess_exec(
            "pdfinfo", "-", stdin=PIPE, stdout=PIPE, stderr=PIPE
        )
        out, _ = await proc.communicate(pdf)
        assert re.search(r"^Title:\s+Mean of y$", out.decode(), re.MULTILINE), out
    assert len(model.calls) == calls  # no model call, no tokens

    # A manuscript that pdfLaTeX cannot compile (even after pandoc normalising) fails
    # with the log instead of returning a broken file.
    from plato.publish import package

    async def broken(tex, name, workdir):
        return False, "! Undefined control sequence.", None

    monkeypatch.setattr(package, "_pdflatex", broken)
    with pytest.raises(PreviewFailed) as err:
        await preview_pdf(store, cid)
    assert "Undefined control sequence" in err.value.log


async def test_unfinished_campaign_is_not_publishable(store):
    _, cid, _, _ = await _new_campaign(store)
    with pytest.raises(NotPublishable):
        await collect(store, cid)


async def test_grant_budget_respects_the_monthly_allowance(store):
    cid, _ = await _completed(store)
    campaign = await store.get_campaign(cid)
    before = campaign["token_budget_max"]
    await grant_budget(store.pool, campaign, 60_000, None)
    after = (await store.get_campaign(cid))["token_budget_max"]
    assert after >= campaign["tokens_used"] + 60_000 and after >= before
    acct = await store.pool.fetchval(
        "INSERT INTO plato.accounts(email, password_hash) VALUES ('a@b.co', repeat('x', 40)) RETURNING id"
    )
    campaign = {**campaign, "account_id": acct}
    with pytest.raises(BudgetExceeded):
        await grant_budget(store.pool, campaign, 60_000, 1_000)


def test_parse_manuscript_round_trip():
    from plato.scientist.nodes import assemble_latex
    from plato.scientist.schemas import Manuscript

    ms = Manuscript(
        title="A & B",
        abstract="abs",
        introduction="intro \\cite{ref_a}",
        methods="m",
        results="r {nested}",
        discussion="d",
        limitations="l",
    )
    title, sections = parse_manuscript(
        assemble_latex(ms, [{"title": "t", "metrics": {}, "confidence_score": None}])
    )
    assert title == "A \\& B"
    assert sections["introduction"] == "intro \\cite{ref_a}"
    assert sections["results"] == "r {nested}"  # the findings table is dropped
    assert sections["limitations"] == "l"


def test_pdf_title_is_plain_text():
    from plato.publish.document import _pdf_title

    assert (
        _pdf_title(r"Coverage of $\beta$ under 95\% \emph{robust} errors \cite{a}")
        == r"Coverage of under 95\% robust errors"
    )
    assert _pdf_title(r"R\&D costs \$5 \{x\}") == r"R\&D costs \$5 x"


def test_sanitize_removes_dangerous_tex():
    text = "ok \\input{/etc/passwd} \\write18{rm -rf /} \\immediate\\write18{x} 50% done \\def\\x{y} \\citep{a, b}"
    out = sanitize(text)
    assert "\\input" not in out and "\\write" not in out and "\\def" not in out
    assert "50\\% done" in out and "\\cite{a,b}" in out
    assert "\\begin{filecontents}" not in sanitize(
        "\\begin{filecontents}{x.tex}evil\\end{filecontents}"
    )
    assert (
        sanitize("α ≤ 0.05 ± 1")
        == "\\ensuremath{\\alpha} \\ensuremath{\\leq} 0.05 \\ensuremath{\\pm} 1"
    )
    assert strip_citations("shown \\cite{a}.") == "shown."
    assert (
        lancet_decimals("p=0.05 and $0.5$ \\cite{ref_1.2}")
        == "p=0\\textperiodcentered{}05 and $0.5$ \\cite{ref_1.2}"
    )


def test_unsupported_numbers_flags_invented_results():
    from types import SimpleNamespace

    m = SimpleNamespace(
        sections={"results": "mean 3.0 (p = 0.01)"},
        title="t",
        nodes=[{"metrics": {"auc": 0.91}}],
    )
    a = JournalAdaptation(
        title="t",
        abstract=[
            AbstractSection(
                heading="Abstract", text="mean 3.0, AUC 0.91, accuracy 97.5%, n=8"
            )
        ],
    )
    assert unsupported_numbers(a, m) == ["97.5%"]


@needs_tex
async def test_service_builds_exports_and_takes_materials(pg_dsn, monkeypatch):
    """Over HTTP: the journal list, materials on create, refusals for unfinished campaigns
    and unknown journals, and a full build when the model is unreachable (fallback)."""
    import base64

    import httpx

    from plato.scientist.service import create_app

    # An unreachable Messages API: the build must still finish, on the fallback front matter.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")
    app = create_app(dsn=pg_dsn, internal_token="t")
    hdr = {"X-Plato-Internal-Token": "t"}
    async with app.router.lifespan_context(app):
        store = app.state.store
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=300
        ) as client:
            j = (await client.get("/internal/publish/journals", headers=hdr)).json()
            assert {x["key"] for x in j} == set(journals.JOURNALS)
            body = {
                "question": "Does y exceed 2?",
                "start": False,
                "materials": [
                    {
                        "file_name": "notes (v2).md",
                        "kind": "document",
                        "content_base64": base64.b64encode(
                            b"# Notes\nSome text."
                        ).decode(),
                    }
                ],
            }
            made = await client.post("/internal/campaigns", json=body, headers=hdr)
            assert made.status_code == 202, made.text
            assert made.json()["materials"] == {
                "references": 0,
                "documents": 1,
                "errors": [],
            }
            bad = dict(
                body, materials=[dict(body["materials"][0], file_name="../x.md")]
            )
            assert (
                await client.post("/internal/campaigns", json=bad, headers=hdr)
            ).status_code == 422
            unfinished = made.json()["id"]
            r = await client.post(
                f"/internal/campaigns/{unfinished}/exports/nature", headers=hdr
            )
            assert r.status_code == 409, r.text

            cid, _ = await _completed(store)
            r = await client.post(
                f"/internal/campaigns/{cid}/exports/nope", headers=hdr
            )
            assert r.status_code == 404
            r = await client.post(
                f"/internal/campaigns/{cid}/exports/arxiv", headers=hdr
            )
            assert r.status_code == 200, r.text
            assert (
                r.headers["x-plato-export-sha256"]
                == hashlib.sha256(r.content).hexdigest()
            )
            export_id = r.headers["x-plato-export-id"]
            assert r.headers["x-plato-export-key"] == f"exports/{cid}/{export_id}.zip"
            row = await store.pool.fetchrow(
                "SELECT status, bytes, summary FROM plato.publication_exports WHERE id = $1::uuid",
                export_id,
            )
            assert row["status"] == "building" and row["bytes"] == len(r.content)
            summary = (
                json.loads(row["summary"])
                if isinstance(row["summary"], str)
                else row["summary"]
            )
            assert summary["adaptation_source"].startswith(
                "fallback: the model call failed"
            )
            assert summary["pdf_ok"] is True
            names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
            top = r.headers["x-plato-export-name"]
            assert f"{top}/manuscript/manuscript.pdf" in names
            assert f"{top}/arxiv/main.tex" in names

            # The typeset paper for the in-app PDF view (no model call).
            r = await client.get(
                f"/internal/campaigns/{cid}/manuscript.pdf", headers=hdr
            )
            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "application/pdf"
            assert (
                r.content.startswith(b"%PDF-")
                and int(r.headers["x-plato-pdf-pages"]) >= 1
            )
            r = await client.get(
                f"/internal/campaigns/{unfinished}/manuscript.pdf", headers=hdr
            )
            assert r.status_code == 409
            r = await client.get(f"/internal/campaigns/{cid}/manuscript.pdf")
            assert r.status_code == 401
