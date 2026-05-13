from plato.config import DESCRIPTION_FILE, IDEA_FILE, INPUT_FILES, REFEREE_FILE
from plato.langgraph_agents.reader import preprocess_node


def test_preprocess_literature_returns_initialized_literature_state(tmp_path):
    input_dir = tmp_path / INPUT_FILES
    input_dir.mkdir()
    (input_dir / DESCRIPTION_FILE).write_text("Synthetic classification benchmark", encoding="utf-8")
    (input_dir / IDEA_FILE).write_text("Compare logistic regression and random forest.", encoding="utf-8")

    state = {
        "task": "literature",
        "files": {
            "Folder": str(tmp_path),
            "data_description": str(input_dir / DESCRIPTION_FILE),
            "idea": str(input_dir / IDEA_FILE),
        },
        "llm": {
            "model": "local-test-model",
            "temperature": 0,
            "max_output_tokens": 1024,
            "stream_verbose": False,
        },
        "keys": object(),
        "literature": {"max_iterations": 4},
        "idea": {"total_iterations": 4},
    }

    update = preprocess_node(state, config={})

    literature = update["literature"]
    assert literature["max_iterations"] == 4
    assert literature["iteration"] == 0
    assert literature["query"] == ""
    assert literature["messages"] == ""
    assert literature["num_papers"] == 0
    assert update["idea"]["idea"] == "Compare logistic regression and random forest."


def test_preprocess_referee_accepts_seeded_idea_state(tmp_path):
    input_dir = tmp_path / INPUT_FILES
    input_dir.mkdir()
    (input_dir / DESCRIPTION_FILE).write_text("Synthetic classification benchmark", encoding="utf-8")

    state = {
        "task": "referee",
        "files": {
            "Folder": str(tmp_path),
            "data_description": str(input_dir / DESCRIPTION_FILE),
        },
        "llm": {
            "model": "local-test-model",
            "temperature": 0,
            "max_output_tokens": 1024,
            "stream_verbose": False,
        },
        "keys": object(),
        "idea": {"total_iterations": 0},
        "referee": {"paper_version": 2},
    }

    update = preprocess_node(state, config={})

    assert update["referee"]["report"] == ""
    assert update["referee"]["images"] == []
    assert update["files"]["referee_report"].endswith(f"/{INPUT_FILES}/{REFEREE_FILE}")
