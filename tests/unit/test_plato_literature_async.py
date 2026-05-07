from contextlib import asynccontextmanager
from types import SimpleNamespace

import plato.langgraph_agents.agents_graph as graph_mod
import plato.plato as plato_mod
from plato.config import DESCRIPTION_FILE, IDEA_FILE, INPUT_FILES, LITERATURE_FILE
from plato.plato import Plato


def test_semantic_scholar_literature_uses_async_graph_invocation(tmp_path, monkeypatch):
    input_dir = tmp_path / INPUT_FILES
    input_dir.mkdir()
    (input_dir / DESCRIPTION_FILE).write_text("Synthetic classification benchmark", encoding="utf-8")
    (input_dir / IDEA_FILE).write_text("Compare logistic regression and random forest.", encoding="utf-8")

    called = {}

    @asynccontextmanager
    async def fake_checkpointer():
        yield object()

    class FakeGraph:
        def invoke(self, *_args, **_kwargs):
            raise AssertionError("literature graph must not use synchronous invoke")

        async def ainvoke(self, state, config):
            called["state"] = state
            called["config"] = config
            literature = tmp_path / INPUT_FILES / LITERATURE_FILE
            literature.write_text("Idea novel\n\nSynthetic benchmark literature summary.", encoding="utf-8")

    def fake_build_lg_graph(*, mermaid_diagram=False, checkpointer=None):
        called["mermaid_diagram"] = mermaid_diagram
        called["checkpointer"] = checkpointer
        return FakeGraph()

    monkeypatch.setattr(plato_mod, "make_async_checkpointer", fake_checkpointer)
    monkeypatch.setattr(graph_mod, "build_lg_graph", fake_build_lg_graph)
    monkeypatch.setattr(
        plato_mod,
        "llm_parser",
        lambda _model: SimpleNamespace(
            name="local-test-model",
            temperature=0,
            max_output_tokens=1024,
        ),
    )

    plato = Plato(project_dir=str(tmp_path))

    result = plato.check_idea_semantic_scholar(llm="local-test-model", max_iterations=1)

    assert "Synthetic benchmark literature summary." in result
    assert called["state"]["literature"]["max_iterations"] == 1
    assert called["config"]["configurable"]["thread_id"]
    assert called["mermaid_diagram"] is False
    assert called["checkpointer"] is not None
