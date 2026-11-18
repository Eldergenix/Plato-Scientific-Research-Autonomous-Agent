"""Workspace tools, recipe runner, document compile and the engineer tool loop.

Everything runs for real against :class:`LocalBackend` (bash in a temp directory);
only E2B itself is out of reach here. The E2B backend is exercised by
``scripts/e2b_lab_verify.py`` against the real service.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import http.server
import io
import json
import shutil
import tarfile
import threading
import uuid
from pathlib import Path

import pytest

from plato.scientist.llm import ToolTurn
from plato.scientist.nodes import (
    code_as_patch,
    code_from_patch,
    recipe_as_patch,
    recipe_from_patch,
)
from plato.scientist.workspace import (
    LocalBackend,
    SessionLimits,
    Workspace,
    run_recipe,
    run_session,
)
from plato.scientist.workspace.compile import (
    CompileError,
    check_pandoc_args,
    compile_command,
    compile_document,
)
from plato.scientist.workspace.tools import TOOL_SPECS, clip


@pytest.fixture
async def ws():
    backend = await LocalBackend.create()
    try:
        yield Workspace(backend)
    finally:
        await backend.close()


async def local_factory(**_):
    return await LocalBackend.create()


@pytest.fixture
def http_root(tmp_path):
    """A local HTTP server standing in for a public dataset host."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield tmp_path, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_tool_specs_are_strict_json_schemas():
    names = [t["name"] for t in TOOL_SPECS]
    assert len(names) == len(set(names)) == 14
    for t in TOOL_SPECS:
        schema = t["input_schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(schema["properties"])
        assert t["description"]


def test_clip_keeps_head_and_tail():
    text = "A" * 10_000 + "END"
    out = clip(text, 1_000)
    assert out.startswith("A") and out.endswith("END") and "elided" in out


async def test_bash_files_edit_and_search(ws):
    r = await ws.call("bash", {"command": "echo hello; echo oops >&2; exit 3"})
    assert "exit code 3" in r.text and "hello" in r.text and "oops" in r.text
    assert not r.is_error  # a failing command is a result, not a tool error

    await ws.call("write_file", {"path": "src/a.py", "content": "x = 1\ny = 2\n"})
    r = await ws.call("list_files", {"path": "."})
    assert "src/a.py" in r.text
    r = await ws.call("read_file", {"path": "src/a.py", "start_line": 2})
    assert "y = 2" in r.text and "x = 1" not in r.text
    r = await ws.call("edit_file", {"path": "src/a.py", "old_text": "y = 2", "new_text": "y = 3"})
    assert not r.is_error
    r = await ws.call("edit_file", {"path": "src/a.py", "old_text": "nope", "new_text": "z"})
    assert r.is_error and "0 times" in r.text
    r = await ws.call("search_files", {"pattern": "y = 3", "path": ".", "glob": "*.py"})
    assert "a.py" in r.text
    r = await ws.call("search_files", {"pattern": "*.py", "names_only": True})
    assert "src/a.py" in r.text

    await ws.backend.write_bytes("blob.bin", bytes(range(256)) * 4)
    r = await ws.call("read_file", {"path": "blob.bin"})
    assert "binary file" in r.text
    r = await ws.call("read_file", {"path": "missing.txt"})
    assert r.is_error


async def test_timeout_is_enforced(ws):
    r = await ws.call("bash", {"command": "sleep 5", "timeout_seconds": 1})
    assert "TIMED OUT" in r.text


async def test_install_rejects_malformed_package_names(ws):
    r = await ws.call("install_packages", {"manager": "pip", "packages": ["numpy; rm -rf /"]})
    assert r.is_error and "invalid package names" in r.text
    r = await ws.call("install_packages", {"manager": "conda", "packages": ["$(evil)"]})
    assert r.is_error
    assert ws.setup_lines == []


async def test_unknown_tool_and_bad_arguments(ws):
    assert (await ws.call("rm_rf", {})).is_error
    r = await ws.call("bash", {"cmd": "ls"})
    assert r.is_error and "bad arguments" in r.text


async def test_download_records_a_verified_recipe(ws, http_root):
    root, base = http_root
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"chr1\t10\t20\n"
        info = tarfile.TarInfo("regions.bed")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    (root / "data.tar.gz").write_bytes(buf.getvalue())
    digest = hashlib.sha256(buf.getvalue()).hexdigest()

    r = await ws.call(
        "download_file",
        {"url": f"{base}/data.tar.gz", "dest": "data/data.tar.gz", "sha256": digest, "extract": True},
    )
    assert not r.is_error, r.text
    assert digest in r.text
    assert (await ws.backend.read_bytes("data/regions.bed")) == b"chr1\t10\t20\n"
    setup = (await ws.backend.read_bytes("setup.sh")).decode()
    assert digest in setup and "sha256sum -c" in setup and "tar -xf" in setup

    # The recipe rebuilds the same files in a fresh sandbox and re-checks the checksum.
    fresh = await LocalBackend.create()
    try:
        await fresh.write_bytes("setup.sh", setup.encode())
        assert (await fresh.run("bash setup.sh")).ok
        assert (await fresh.read_bytes("data/regions.bed")).startswith(b"chr1")
        (root / "data.tar.gz").write_bytes(b"tampered")
        await fresh.run("rm -rf data")
        assert not (await fresh.run("bash setup.sh")).ok
    finally:
        await fresh.close()


async def test_download_rejects_bad_input_and_checksum(ws, http_root):
    root, base = http_root
    (root / "f.txt").write_text("x")
    assert (await ws.call("download_file", {"url": "file:///etc/passwd", "dest": "p"})).is_error
    assert (await ws.call("download_file", {"url": f"{base}/f.txt", "dest": "../x"})).is_error
    r = await ws.call("download_file", {"url": f"{base}/f.txt", "dest": "f.txt", "sha256": "0" * 64})
    assert r.is_error and "checksum mismatch" in r.text
    assert not (await ws.backend.run("test -e f.txt")).ok
    r = await ws.call("download_file", {"url": f"{base}/missing", "dest": "m"})
    assert r.is_error
    assert ws.setup_lines == []


async def test_background_jobs(ws):
    r = await ws.call("start_job", {"name": "count", "command": "for i in 1 2 3; do echo n$i; sleep 0.2; done"})
    assert not r.is_error, r.text
    r = await ws.call("wait_job", {"name": "count", "max_wait_seconds": 20})
    assert "exited with code 0" in r.text and "n3" in r.text
    assert (await ws.call("start_job", {"name": "count", "command": "true"})).is_error

    await ws.call("start_job", {"name": "long", "command": "sleep 60"})
    r = await ws.call("job_status", {"name": "long"})
    assert "running" in r.text
    r = await ws.call("stop_job", {"name": "long"})
    assert not r.is_error
    r = await ws.call("job_status", {"name": "long"})
    assert "exited with code 143" in r.text
    assert (await ws.call("job_status", {"name": "nope"})).is_error
    assert (await ws.call("start_job", {"name": "bad name;", "command": "true"})).is_error


def test_compile_commands_and_pandoc_allow_list():
    cmd, out = compile_command("paper/main.tex", "pdf")
    assert out == "paper/main.pdf" and "latexmk -pdf" in cmd and "-no-shell-escape" in cmd
    cmd, out = compile_command("main.tex", "pdf", "xelatex")
    assert "-xelatex" in cmd
    cmd, out = compile_command("m.md", "docx", "pandoc", ["--citeproc", "--csl", "nature.csl"])
    assert out == "m.docx" and "--csl=nature.csl" in cmd
    _, out = compile_command("m.md", "jats")
    assert out == "m.xml"
    for bad in (["--lua-filter=x.lua"], ["--filter", "x"], ["--csl=/etc/passwd"], ["-o", "x"]):
        with pytest.raises(CompileError):
            check_pandoc_args(bad)
    with pytest.raises(CompileError):
        compile_command("../main.tex", "pdf")
    with pytest.raises(CompileError):
        compile_command("main.md", "pdf", "latexmk")


@pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc not installed")
async def test_compile_document_with_pandoc():
    res = await compile_document(
        {"note.md": b"# Title\n\nSome *text*.\n"},
        main="note.md",
        target="html",
        backend_factory=local_factory,
    )
    assert res.ok, res.log
    assert b"<em>text</em>" in res.output


@pytest.mark.skipif(not shutil.which("latexmk"), reason="latexmk not installed")
async def test_compile_document_latex_to_pdf():
    tex = rb"\documentclass{article}\begin{document}Hello $x^2$.\end{document}"
    res = await compile_document({"main.tex": tex}, main="main.tex", backend_factory=local_factory)
    assert res.ok, res.log
    assert res.output.startswith(b"%PDF")


async def test_compile_reports_failures_without_raising():
    res = await compile_document(
        {"main.tex": rb"\documentclass{article}\begin{document}\undefinedmacro\end{document}"},
        main="main.tex",
        backend_factory=local_factory,
    )
    assert not res.ok and res.output == b""


def test_recipe_patch_round_trip_with_diff_like_content():
    code = 'print("--- /dev/null")\nprint("+++ b/x")\n@@ -0,0 +1,2 @@\n'
    setup = "set -e\ncurl -o a.txt https://example.org/a.txt\n"
    patch = recipe_as_patch(code, setup)
    assert recipe_from_patch(patch) == (code.rstrip("\n"), setup.rstrip("\n"))
    assert code_from_patch(patch) == code.rstrip("\n")
    legacy = code_as_patch("x = 1\ny = 2")
    assert recipe_from_patch(legacy) == ("x = 1\ny = 2", None)
    assert recipe_as_patch("x = 1", None) == code_as_patch("x = 1")


EXPERIMENT = """
import json
seed = int(open("plato_seed.txt").read())
factor = int(open("factor.txt").read())
open("out.csv", "w").write("a,b\\n1,2\\n")
print("PLATO_METRICS", json.dumps({"value": factor * seed}))
"""


async def test_run_recipe_rebuilds_environment_then_runs_offline():
    res = await run_recipe(
        local_factory,
        code=EXPERIMENT,
        setup="set -e\necho 3 > factor.txt\n",
        inputs={"plato_seed.txt": b"2"},
        setup_seconds=30,
        run_seconds=30,
    )
    assert res.ok, res.stderr
    assert res.stdout.strip().endswith('{"value": 6}')
    assert set(res.files) == {"out.csv"}  # inputs, scripts and the setup artefact excluded
    assert res.network_isolated is False  # LocalBackend cannot enforce it, and says so

    failed = await run_recipe(
        local_factory,
        code=EXPERIMENT,
        setup="exit 4\n",
        inputs={"plato_seed.txt": b"1"},
        setup_seconds=30,
        run_seconds=30,
    )
    assert not failed.ok and "setup.sh exited with code 4" in failed.stderr

    with pytest.raises(ValueError):
        await run_recipe(
            local_factory, code="", setup=None, inputs={"setup.sh": b""}, setup_seconds=5, run_seconds=5
        )


class ScriptedEngineer:
    """A fake model whose tool calls follow a fixed script."""

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[list] = []

    async def converse(self, *, campaign_id, purpose, system, messages, tools, max_tokens, effort):
        self.requests.append([dict(m) for m in messages])
        assert tools is TOOL_SPECS
        step = self.script.pop(0)
        if step is None:
            return ToolTurn([{"type": "text", "text": "thinking aloud"}], "end_turn", [], "thinking aloud")
        uses = [(f"tu_{uuid.uuid4().hex[:8]}", name, args) for name, args in step]
        content = [{"type": "tool_use", "id": i, "name": n, "input": a} for i, n, a in uses]
        return ToolTurn(content, "tool_use", uses, "")


async def test_session_runs_tools_and_ends_on_accepted_submission(ws):
    submitted = []

    async def on_submit(code, setup):
        submitted.append((code, setup))
        if "factor.txt" not in setup:
            return ("Rejected: factor.txt missing in the fresh sandbox", False, None)
        return ("Accepted", True, {"ok": True})

    ws.on_submit = on_submit
    model = ScriptedEngineer(
        [
            [("bash", {"command": "echo 3 > factor.txt"}), ("write_file", {"path": "experiment.py", "content": EXPERIMENT})],
            [("submit_experiment", {"experiment_path": "experiment.py"})],
            None,  # a turn without tools gets a nudge, not the end
            [
                ("write_file", {"path": "setup.sh", "content": "echo 3 > factor.txt\n"}),
                ("submit_experiment", {"experiment_path": "experiment.py", "setup_path": "setup.sh"}),
            ],
        ]
    )
    out = await run_session(
        model=model,
        campaign_id=uuid.uuid4(),
        system="sys",
        task="do it",
        workspace=ws,
        nonce="abc123",
        limits=SessionLimits(max_turns=6),
    )
    assert out.submitted == {"ok": True} and out.reason == "submitted" and out.turns == 4
    assert len(submitted) == 2
    # Tool results are framed as untrusted output and returned in one user message per turn.
    second = model.requests[1][-1]
    assert second["role"] == "user" and len(second["content"]) == 2
    assert all(b["type"] == "tool_result" and "<untrusted-abc123" in b["content"] for b in second["content"])
    rejected = model.requests[2][-1]["content"][0]
    assert rejected["is_error"] is True and "factor.txt missing" in rejected["content"]
    assert "Continue working" in model.requests[3][-1]["content"]


async def test_session_gives_up_after_stalls_and_turn_cap(ws):
    out = await run_session(
        model=ScriptedEngineer([None, None, None]),
        campaign_id=uuid.uuid4(),
        system="s",
        task="t",
        workspace=ws,
        nonce="n",
        limits=SessionLimits(max_turns=10, max_stalls=2),
    )
    assert out.submitted is None and out.reason == "stopped without submitting" and out.turns == 3
    model = ScriptedEngineer([[("bash", {"command": "true"})]] * 3)
    out = await run_session(
        model=model, campaign_id=uuid.uuid4(), system="s", task="t", workspace=ws, nonce="n",
        limits=SessionLimits(max_turns=3),
    )
    assert out.reason == "turn limit reached"
    assert "turn(s) left" in json.dumps(model.requests[-1][-1]["content"], default=str)


def test_lab_template_definition_is_consistent():
    pytest.importorskip("e2b")
    from e2b import Template

    from plato.scientist.workspace import lab

    dockerfile = Template.to_dockerfile(lab.lab_template())
    for env, (_, _, exes) in lab.CONDA_TOOL_ENVS.items():
        assert f"-n {env} " in dockerfile
        for exe in exes:
            assert f"/opt/conda/bin/{exe}" in dockerfile and exe.split(".")[0].lower() in lab.LAB_SUMMARY.lower()
    assert "/etc/profile.d/plato-lab.sh" in dockerfile
    assert "E2B" not in dockerfile and "API_KEY" not in dockerfile  # no secrets baked in


async def test_local_backend_paths_and_network_flag():
    b = await LocalBackend.create()
    try:
        await b.write_bytes("d/x.txt", b"1")
        assert Path(b.workdir, "d/x.txt").read_bytes() == b"1"
        assert await b.set_network(False) is False
        out = await b.run("pwd")
        assert out.stdout.strip() == b.workdir
    finally:
        await b.close()
    assert not Path(b.workdir).exists()


async def test_concurrent_sessions_do_not_share_state():
    a, c = await asyncio.gather(LocalBackend.create(), LocalBackend.create())
    try:
        await a.write_bytes("f", b"a")
        assert not (await c.run("test -e f")).ok
    finally:
        await a.close()
        await c.close()


# ---------------------------------------------------------------------------
# A whole campaign with executor "e2b" (workspaces on LocalBackend)
# ---------------------------------------------------------------------------

WORKSPACE_CODE = (
    "factor = int(open('factor.txt').read())\nassert factor == 3\n"
)


class WorkspaceFakeModel:
    """FakeModel from the end-to-end suite plus a scripted research engineer."""

    def __new__(cls, store):
        from test_end_to_end import GOOD_CODE, FakeModel

        class _M(FakeModel):
            async def converse(self, *, campaign_id, purpose, system, messages, tools, max_tokens, effort):
                await self.store.reserve_tokens(campaign_id, self.per_call)
                self.calls.append(purpose)
                assert "<untrusted-" in system or "untrusted" in system
                turn = sum(1 for m in messages if m["role"] == "assistant")
                task = messages[0]["content"]
                assert "plato-lab" in task and "train.csv" in task
                code = WORKSPACE_CODE + GOOD_CODE
                script = [
                    [("list_files", {"path": "."}), ("read_file", {"path": "train.csv"})],
                    [("write_file", {"path": "experiment.py", "content": code})],
                    # The factor file exists only in this workspace: the fresh re-run must fail.
                    [("bash", {"command": "echo 3 > factor.txt"}),
                     ("submit_experiment", {"experiment_path": "experiment.py"})],
                    [("write_file", {"path": "setup.sh", "content": "set -e\necho 3 > factor.txt\n"}),
                     ("submit_experiment", {"experiment_path": "experiment.py", "setup_path": "setup.sh"})],
                ]
                step = script[min(turn, len(script) - 1)]
                uses = [(f"tu{turn}_{i}", n, a) for i, (n, a) in enumerate(step)]
                return ToolTurn(
                    [{"type": "tool_use", "id": i, "name": n, "input": a} for i, n, a in uses],
                    "tool_use", uses, "",
                )

        return _M(store)


async def test_campaign_with_e2b_executor_records_reproducible_recipes(store):
    from test_end_to_end import _new_campaign, fake_retriever

    from plato.scientist.graph import run_campaign
    from plato.scientist.nodes import ScientistContext

    program = await store.ensure_program("e2e", "E2E", "statistics")
    cid = await store.create_campaign(
        program,
        "Is the average of y greater than 2?",
        token_budget_max=1_000_000,
        config={"workers": 2, "max_rounds": 1, "executor": "e2b"},
    )
    train = await store.put_dataset(program, "train.csv", b"x,y\n1,2\n2,3\n3,4\n")
    holdout = await store.put_dataset(program, "holdout.csv", b"x,y\n1,10\n2,12\n", is_sealed_eval=True)
    await store.set_scope(cid, train.id, "train_val")
    await store.set_scope(cid, holdout.id, "sealed_eval_only")
    del _new_campaign

    model = WorkspaceFakeModel(store)
    ctx = ScientistContext(store=store, model=model, retriever=fake_retriever, backend_factory=local_factory)
    summary = await run_campaign(ctx, cid)
    assert summary["campaign"]["status"] == "completed", summary["campaign"]
    assert "workspace_engineer" in model.calls and "write_experiment" not in model.calls

    findings = await store.nodes(cid, node_type="finding", status="verified")
    assert findings, "the recipe-backed fact should replicate and be promoted"
    # Sealed evaluation replayed the recipe (the factor assert would fail otherwise).
    assert findings[0]["metrics"]["sealed_eval"] == {"sealed_mean_y": 11.0}

    facts = await store.nodes(cid, node_type="fact")
    fact = next(f for f in facts if f["status"] == "verified")
    assert fact["metrics"]["executor"] == "e2b"
    assert fact["metrics"]["replication"]["mean_y"] == 3.0
    patch = (await store.evidence_contents(fact["id"], "git_patch"))[0].decode()
    code, setup = recipe_from_patch(patch)
    assert "factor.txt" in setup and code.startswith("factor = int")

    intents = await store.nodes(cid, node_type="intent")
    logs = [
        json.loads(x.decode()[len("WORKSPACE SESSION "):])
        for i in intents
        for x in await store.evidence_contents(i["id"], "stdout_log")
        if x.startswith(b"WORKSPACE SESSION ")
    ]
    assert logs and all(log["end"] == "submitted" and log["submissions"] == 2 for log in logs)
    assert all(log["sandbox"].startswith("local-") for log in logs)
    assert {a["tool"] for a in logs[0]["actions"]} >= {"list_files", "read_file", "write_file", "submit_experiment"}
    camp = await store.get_campaign(cid)
    assert camp["gpu_seconds_used"] > 0


async def test_session_ends_when_submissions_are_exhausted(ws):
    calls = []

    async def on_submit(code, setup):
        calls.append(code)
        ws.exhausted = True  # the pipeline's last allowed attempt failed
        return ("Rejected: metrics missing", False, None)

    ws.on_submit = on_submit
    await ws.backend.write_bytes("experiment.py", b"print(1)\n")
    model = ScriptedEngineer([[("submit_experiment", {"experiment_path": "experiment.py"})]] * 5)
    out = await run_session(
        model=model, campaign_id=uuid.uuid4(), system="s", task="t", workspace=ws, nonce="n",
        limits=SessionLimits(max_turns=5),
    )
    assert out.reason == "submissions exhausted" and out.turns == 1 and len(calls) == 1


class _Usage:
    def __init__(self, i, o, cw, cr):
        self.input_tokens, self.output_tokens = i, o
        self.cache_creation_input_tokens, self.cache_read_input_tokens = cw, cr


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class _BudgetStore:
    def __init__(self):
        self.reserved, self.settled = [], []

    async def reserve_tokens(self, campaign_id, n, *, keep_free=0):
        self.reserved.append((n, keep_free))

    async def settle_tokens(self, campaign_id, reserved, actual):
        self.settled.append((reserved, actual))


def _model_with(response):
    from plato.scientist.llm import AnthropicScientistModel

    store = _BudgetStore()
    client = type("C", (), {})()
    client.messages = _FakeMessages(response)
    model = AnthropicScientistModel(store, model="claude-haiku-5-5", client=client)
    return model, store, client.messages


async def test_converse_caches_prefix_and_settles_actual_usage():
    thinking = _Block(type="thinking", thinking="", signature="sig")
    use = _Block(type="tool_use", id="tu_1", name="bash", input={"command": "ls"})
    response = _Block(
        content=[thinking, _Block(type="text", text="Listing."), use],
        stop_reason="tool_use",
        usage=_Usage(1200, 300, 5000, 40001),
    )
    model, store, messages = _model_with(response)
    msgs = [{"role": "user", "content": "go"}]
    turn = await model.converse(
        campaign_id=uuid.uuid4(), purpose="workspace_engineer", system="sys",
        messages=msgs, tools=TOOL_SPECS, max_tokens=4000, effort="medium",
    )
    assert turn.tool_uses == [("tu_1", "bash", {"command": "ls"})] and turn.text == "Listing."
    # The whole response goes back unchanged so thinking signatures survive the next turn.
    assert turn.content[0] is thinking
    kw = messages.kwargs
    assert kw["cache_control"] == {"type": "ephemeral"} and kw["tools"] is TOOL_SPECS
    assert kw["tool_choice"] == {"type": "auto"} and kw["output_config"] == {"effort": "medium"}
    (reserved, keep_free), = store.reserved
    assert reserved >= 4000 and keep_free == 80_000
    # input + output + cache writes + cache reads at a tenth (rounded up).
    assert store.settled == [(reserved, 1200 + 300 + 5000 + 4001)]


async def test_converse_refusal_raises_and_still_settles():
    from plato.scientist.llm import ModelRefusal

    response = _Block(content=[], stop_reason="refusal", usage=_Usage(10, 0, 0, 0),
                      stop_details=_Block(category="cyber"))
    model, store, _ = _model_with(response)
    with pytest.raises(ModelRefusal):
        await model.converse(
            campaign_id=uuid.uuid4(), purpose="p", system="s",
            messages=[{"role": "user", "content": "x"}], tools=TOOL_SPECS,
        )
    assert store.settled and store.settled[0][1] == 10
