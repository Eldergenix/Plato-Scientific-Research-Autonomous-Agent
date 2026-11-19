"""An intent's design round-trips as fields, never as a JSON blob in the hypothesis.

The fixture is the stored text of a real intent that the app showed as raw JSON. The app's
reader (cloudflare/plato-scientist/public/app/spec.js) is checked against the same fixture in
e2e/unit.test.mjs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plato.scientist.schemas import (
    IntentBatch,
    IntentSpec,
    decode_intent_spec,
    encode_intent_spec,
)

STORED = (Path(__file__).parent / "fixtures" / "intent_design.json").read_text().strip()
DESIGN = json.loads(STORED)


def _spec(**over) -> IntentSpec:
    base = {
        **DESIGN,
        "title": "Pathology confounding",
        "priority": 0.7,
        "goal_index": 0,
    }
    return IntentSpec.model_validate({**base, **over})


def test_stored_design_decodes_to_fields():
    assert decode_intent_spec(STORED) == DESIGN


def test_encode_matches_the_stored_row_and_round_trips():
    spec = _spec()
    text = encode_intent_spec(spec, DESIGN["primary_metric"])
    assert text == STORED
    assert decode_intent_spec(text) == DESIGN


def test_double_encoded_row_decodes():
    assert decode_intent_spec(json.dumps(STORED)) == DESIGN


def test_design_nested_in_hypothesis_decodes():
    row = json.dumps({"hypothesis": STORED, "protocol": "", "primary_metric": "x"})
    got = decode_intent_spec(row)
    assert got["hypothesis"] == DESIGN["hypothesis"]
    assert got["protocol"] == DESIGN["protocol"]
    assert got["primary_metric"] == "x"  # the outer value wins where it is set
    assert got["success_criterion"] == DESIGN["success_criterion"]


@pytest.mark.parametrize(
    "text", ["A plain claim.", "[1, 2]", "{not json", '{"title": "x"}']
)
def test_text_without_a_design_raises(text):
    with pytest.raises(ValueError):
        decode_intent_spec(text)


def test_model_output_with_encoded_design_in_hypothesis_is_unwrapped():
    spec = _spec(hypothesis=STORED, protocol="", success_criterion="")
    assert spec.hypothesis == DESIGN["hypothesis"]
    assert spec.protocol == DESIGN["protocol"]
    assert spec.success_criterion == DESIGN["success_criterion"]
    assert decode_intent_spec(encode_intent_spec(spec, spec.primary_metric)) == DESIGN


def test_model_output_unwrapped_through_the_batch_parser():
    raw = json.dumps(
        {
            "intents": [
                {
                    **DESIGN,
                    "hypothesis": json.dumps(STORED),
                    "title": "t",
                    "priority": 0.5,
                    "goal_index": 0,
                }
            ]
        }
    )
    (spec,) = IntentBatch.model_validate_json(raw).intents
    assert spec.hypothesis == DESIGN["hypothesis"]


def test_plain_hypothesis_is_left_alone():
    assert (
        _spec(hypothesis="{Braces} in prose stay as written.").hypothesis
        == "{Braces} in prose stay as written."
    )
