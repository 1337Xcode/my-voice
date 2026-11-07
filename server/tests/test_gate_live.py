"""Live checks of the gate against the real TypeSafe, OpenAI and Anthropic APIs; each runs only when its key is set."""

import asyncio
import os
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.live

import voice.storage as storage
from voice.gate.act import GateSettings
from voice.gate.candidates import Hypothesis, PhraseMatch, build_candidates
from voice.gate.decide import DecisionError, decide
from voice.gate.pipeline import run_gate
from voice.gate.repair import repair
from voice.gate.static_block import build_static_block

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
NBEST = [Hypothesis("can I have a fat white please", -0.42), Hypothesis("can I have a flat white please", -0.55),
         Hypothesis("can I half a flat way please", -0.91)]
PHRASES = [PhraseMatch("p11", "Can I have a flat white, please?", 0.18, 0.74, 0.31)]
CONVERSATION = ["them: Hi there, what can I get you?"]


def env_file_values() -> dict[str, str]:
    """Reads KEY=value lines from the repo .env without printing them."""
    if not ENV_FILE.exists():
        return {}
    pairs = (line.split("=", 1) for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
             if "=" in line and not line.lstrip().startswith("#"))
    return {key.strip(): value.strip().strip("'\"") for key, value in pairs}


ENV = env_file_values()


def needs(variable: str):
    """Skips the test unless the key is set in the environment or the repo .env."""
    return pytest.mark.skipif(not (os.environ.get(variable) or ENV.get(variable)), reason=f"{variable} is not set")


@pytest.fixture(autouse=True)
def live_env(tmp_path, monkeypatch):
    for key, value in ENV.items():
        if value and not os.environ.get(key):
            monkeypatch.setenv(key, value)
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)


def flat_white_wins(decision) -> bool:
    """True when the flat white sentence has the top probability."""
    candidates = build_candidates(NBEST, PHRASES, [])
    flat = next(c.id for c in candidates if c.text == "Can I have a flat white, please?")
    return max(decision.probabilities, key=decision.probabilities.get) == flat


@needs("TYPESAFE_API_KEY")
def test_jev_picks_the_flat_white():
    decision = asyncio.run(decide("jev", build_static_block("P1"), CONVERSATION, build_candidates(NBEST, PHRASES, [])))
    print(f"jev {decision.model}: {decision.ms} ms, {decision.probabilities}")
    assert decision.model.startswith("jev-")
    assert flat_white_wins(decision)


@needs("OPENAI_API_KEY")
def test_openai_decisions_picks_the_flat_white():
    try:
        decision = asyncio.run(decide("openai", build_static_block("P1"), CONVERSATION, build_candidates(NBEST, PHRASES, [])))
    except DecisionError as exc:
        if "geography restrictions" in str(exc):
            pytest.skip(f"OPENAI_BASE_URL is refused for this project: {exc}")
        raise
    print(f"openai {decision.model}: {decision.ms} ms, {decision.probabilities}, usage {decision.raw_usage}")
    assert flat_white_wins(decision)


@needs("ANTHROPIC_API_KEY")
def test_haiku_repairs_within_its_budget():
    async def warm_then_repair():
        # Serving warms the connection and the prompt cache when the app says hello; the timed call comes after.
        async with httpx.AsyncClient() as http:
            await repair(build_static_block("P1"), [], CONVERSATION, NBEST, PHRASES, http, timeout_s=15.0)
            return await repair(build_static_block("P1"), [], CONVERSATION, NBEST, PHRASES, http)

    result = asyncio.run(warm_then_repair())
    if result.error and "ANTHROPIC_API_KEY is wrong" in result.error:
        pytest.skip(result.error)
    print(f"repair: {result.ms} ms, {result.sentences}, {result.error}, usage {result.usage}")
    assert result.error is None
    assert "Can I have a flat white, please?" in result.sentences


@needs("TYPESAFE_API_KEY")
def test_full_gate_acts_and_never_speaks_a_wrong_sentence():
    started = time.perf_counter()
    result = asyncio.run(run_gate("P1", NBEST, PHRASES, CONVERSATION, GateSettings(), "jev"))
    print(f"gate: {round((time.perf_counter() - started) * 1000)} ms, {result.action}, {result.timings}, {result.errors}")
    assert "round1" not in result.errors
    texts = {c.id: c.text for c in result.candidates}
    if result.action == "speak":
        assert texts[result.chosen_id] == "Can I have a flat white, please?"
    else:
        assert result.action == "pick" and texts[result.shown_ids[0]] == "Can I have a flat white, please?"


@needs("TYPESAFE_API_KEY")
def test_unsure_turn_waits_for_repair_and_never_speaks_a_missing_sentence():
    nbest = [Hypothesis("where is the nation please", -0.7), Hypothesis("wear is the station please", -0.8),
             Hypothesis("where is this station please", -0.9)]
    result = asyncio.run(run_gate("P1", nbest, [], [], GateSettings(), "jev"))
    print(f"unsure gate: {result.action}, {result.timings}, {result.errors}, {[(c.text, c.p) for c in result.candidates]}")
    assert result.timings["t_round1"] is not None and result.timings["t_repair"] is not None
    if result.action == "speak":
        assert "repair" in next(c for c in result.candidates if c.id == result.chosen_id).sources
    if "repair" in result.errors:
        assert result.timings["t_round2"] is None and result.action in ("pick", "again")
