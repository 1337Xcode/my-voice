"""Repair's request shape and output checks; the live call is in test_gate_live.py."""

import json

import pytest
from pydantic import ValidationError

from voice.gate.candidates import Hypothesis, PhraseMatch
from voice.gate.repair import RepairError, build_request, parse_output


def reply(sentences) -> dict:
    """A Messages response carrying the given structured output."""
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps({"sentences": sentences})}]}


def test_request_caches_the_static_block_and_asks_for_structured_output():
    body = build_request("STATIC", [{"heard": "fat white", "meant": "Flat white."}], ["them: hi"],
                         [Hypothesis("a fat white", -0.4)], [PhraseMatch("p11", "A flat white.", 0.2, 0.7, 0.3)])
    assert body["model"] == "claude-haiku-5-5"
    assert body["system"][0]["text"].endswith("STATIC") and body["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert body["output_config"]["effort"] == "low" and body["output_config"]["format"]["type"] == "json_schema"
    turn = json.loads(body["messages"][0]["content"])
    assert turn["hypotheses"] == [{"label": "h1", "text": "a fat white", "logprob": -0.4}]
    assert turn["phrase_matches"][0]["label"] == "p11"
    assert turn["past_corrections"] == [{"recogniser_heard": "fat white", "he_meant": "Flat white."}]


def test_only_grounded_sentences_are_kept_and_at_most_three():
    sentences = [{"text": "A flat white.", "based_on": ["h1", "p11"]}, {"text": "Invented.", "based_on": ["h9"]},
                 {"text": "Two.", "based_on": ["h2"]}, {"text": "Three.", "based_on": ["h1"]}, {"text": "Four.", "based_on": ["h1"]}]
    assert parse_output(reply(sentences), {"h1", "h2", "p11"}) == ["A flat white.", "Two.", "Three."]


def test_malformed_output_raises_validation_error_and_refusal_raises_repair_error():
    with pytest.raises(ValidationError):
        parse_output({"content": [{"type": "text", "text": '{"sentences": "nope"}'}]}, {"h1"})
    with pytest.raises(RepairError):
        parse_output({"stop_reason": "refusal", "content": []}, {"h1"})
