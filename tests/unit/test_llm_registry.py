"""Model registry: retired Claude ids resolve to their successors, with a warning."""

import pytest

from plato.llm import RETIRED_ALIASES, models
from plato.utils import llm_parser


@pytest.mark.parametrize("old,new", sorted(RETIRED_ALIASES.items()))
def test_retired_aliases_resolve_to_successor_with_warning(old, new):
    with pytest.warns(DeprecationWarning, match="retired"):
        assert llm_parser(old) is models[new]


def test_current_claude_models_send_no_temperature():
    for key in ("claude-haiku-5.5", "claude-sonnet-5.5", "claude-opus-5.5"):
        assert models[key].temperature is None
    assert models["claude-haiku-5-5"].name == "claude-haiku-5-5"
