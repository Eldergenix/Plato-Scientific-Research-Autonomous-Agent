import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from ..paper_agents.tools import extract_latex_block, LLM_call_stream, clean_section
from .prompts import idea_maker_prompt, idea_hater_prompt
from .parameters import GraphState


def _append_transcript_turn(state: GraphState, agent: str, text: str) -> None:
    """Append one JSON-line turn to ``idea_transcript.jsonl``.

    The dashboard's IdeaStage TranscriptPane needs structured turn
    boundaries (agent / iteration / ts / text) to render the maker-hater
    debate, but ``idea.log`` is just concatenated streaming tokens with
    no separator. This sidecar stays alongside it so a future reader can
    replay the conversation cell-by-cell.

    Best-effort: never raises. The pipeline is the source of truth; this
    file is observability only.
    """
    files = state.get('files') or {}
    folder = files.get('Folder')
    if not folder:
        return
    try:
        path = Path(folder) / 'idea_generation_output' / 'idea_transcript.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "agent": agent,
                "text": text,
                "ts": datetime.now(timezone.utc).isoformat(),
                "iteration": state['idea'].get('iteration'),
            },
            ensure_ascii=False,
        )
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception:
        # Observability writes never break the pipeline.
        pass


def idea_maker(state: GraphState, config: RunnableConfig):

    print(f"Maker (iteration {state['idea']['iteration']+1})")

    PROMPT = idea_maker_prompt(state)
    state, result = LLM_call_stream(PROMPT, state, node_name="idea_maker")
    text = extract_latex_block(state, result, "IDEA")

    # remove LLM added lines
    text = clean_section(text, "IDEA")

    _append_transcript_turn(state, "idea_maker", text)

    # Build the new ``idea`` dict immutably. Mutating ``state['idea']``
    # in-place AND returning it as the partial update breaks the
    # checkpointer's snapshot semantics — LangGraph stores the previous
    # snapshot by reference, so an in-place mutation rewrites history
    # under SqliteSaver/PostgresSaver. The fix is to return a fresh dict.
    new_iter = state['idea']['iteration'] + 1
    new_idea = {
        **state['idea'],
        'idea': text,
        'previous_ideas': (
            f"{state['idea']['previous_ideas']}\n\n"
            f"Iteration {state['idea']['iteration']}:\n"
            f"Idea: {text}\n"
        ),
        'iteration': new_iter,
    }

    if new_iter == state['idea']['total_iterations']:
        with open(state['files']['idea'], 'w') as f:
            f.write(text)

        print(f"done {state['tokens']['ti']} {state['tokens']['to']}")

    return {"idea": new_idea}


def idea_hater(state: GraphState, config: RunnableConfig):

    print(f"Hater (iteration {state['idea']['iteration']})")

    PROMPT = idea_hater_prompt(state)
    state, result = LLM_call_stream(PROMPT, state, node_name="idea_hater")
    text = extract_latex_block(state, result, "CRITIC")

    # remove LLM added lines
    text = clean_section(text, "CRITIC")

    _append_transcript_turn(state, "idea_hater", text)

    # Same immutable-update pattern as idea_maker — never mutate state
    # in-place when returning the value as the LangGraph state update.
    new_idea = {**state['idea'], 'criticism': text}

    return {"idea": new_idea}


