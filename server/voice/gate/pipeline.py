"""One turn through the gate: candidates, round 1 with repair in parallel, round 2, act (spec 8.5 to 8.8), and learning (9.1)."""

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from voice.config import MissingKey
from voice.gate.act import GateSettings, choose_action, is_confident
from voice.gate.candidates import Candidate, Hypothesis, MemoryHit, PhraseMatch, build_candidates
from voice.gate.decide import Decision, DecisionError, decide
from voice.gate.memory import add_pair, lookup, similar_pairs
from voice.gate.repair import repair
from voice.gate.static_block import build_static_block


@dataclass(frozen=True)
class GateCandidate:
    """A candidate as the app and the turn record see it."""

    id: str
    text: str
    p: float | None
    sources: list[str]


@dataclass
class GateResult:
    """What the gate decided for one turn, with every candidate, timing and error."""

    action: str
    shown_ids: list[str]
    candidates: list[GateCandidate]
    chosen_id: str | None
    # Milliseconds from the start of the gate to the end of each step; None when the step did not run.
    timings: dict[str, int | None] = field(default_factory=lambda: {"t_round1": None, "t_repair": None, "t_round2": None})
    provider: str = ""
    model: str = ""
    errors: dict[str, str] = field(default_factory=dict)


def _elapsed_ms(started: float) -> int:
    """Milliseconds since the gate started."""
    return round((time.perf_counter() - started) * 1000)


def _result(candidates: list[Candidate], decision: Decision | None, settings: GateSettings, result: GateResult) -> GateResult:
    """Fills in the action and the candidates, most likely first; with no decision the action is 'again'."""
    probabilities = decision.probabilities if decision else {}
    action = choose_action(probabilities, settings) if decision else None
    result.action = action.kind if action else "again"
    result.shown_ids = action.ids if action else [c.id for c in candidates[:1]]
    result.chosen_id = result.shown_ids[0] if result.action in ("speak", "pick") else None
    ordered = sorted(candidates, key=lambda c: probabilities.get(c.id, -1.0), reverse=True)
    result.candidates = [GateCandidate(c.id, c.text, probabilities.get(c.id), list(c.sources)) for c in ordered]
    if decision:
        result.provider, result.model = decision.provider, decision.model
    return result


async def _second_round(turn: tuple, repair_task: asyncio.Task, first: Decision, candidates: list[Candidate],
                        settings: GateSettings, result: GateResult, started: float, http: httpx.AsyncClient) -> GateResult:
    """Waits for repair, adds its sentences as candidates and decides again; keeps round 1 if round 2 cannot run."""
    static, conversation, nbest, phrases, hits, provider = turn
    fixed = await repair_task
    result.timings["t_repair"] = _elapsed_ms(started)
    if fixed.error:
        result.errors["repair"] = fixed.error
    if not fixed.sentences:
        return _result(candidates, first, settings, result)
    widened = build_candidates(nbest, phrases, hits, fixed.sentences)
    try:
        second = await decide(provider, static, conversation, widened, http)
    except (DecisionError, MissingKey) as exc:
        result.errors["round2"] = str(exc)
        return _result(candidates, first, settings, result)
    result.timings["t_round2"] = _elapsed_ms(started)
    return _result(widened, second, settings, result)


async def _run(speaker: str, nbest: list[Hypothesis], phrases: list[PhraseMatch], conversation: list[str],
               settings: GateSettings, provider: str, http: httpx.AsyncClient) -> GateResult:
    """Steps: gather candidates; start repair and round 1 together; act on a confident round 1, else run round 2."""
    started = time.perf_counter()
    heard = nbest[0].text if nbest else ""
    hits: list[MemoryHit] = lookup(speaker, heard)
    candidates = build_candidates(nbest, phrases, hits)
    result = GateResult(action="again", shown_ids=[], candidates=[], chosen_id=None)
    if not candidates:
        return result
    static = build_static_block(speaker)
    examples = [pair for pair, _ in similar_pairs(speaker, heard)] if heard else []
    repair_task = asyncio.create_task(repair(static, examples, conversation, nbest, phrases, http))
    try:
        try:
            first = await decide(provider, static, conversation, candidates, http)
        except (DecisionError, MissingKey) as exc:
            result.errors["round1"] = str(exc)
            return _result(candidates, None, settings, result)
        result.timings["t_round1"] = _elapsed_ms(started)
        if is_confident(first.probabilities, settings):
            return _result(candidates, first, settings, result)
        parts = (static, conversation, nbest, phrases, hits, provider)
        return await _second_round(parts, repair_task, first, candidates, settings, result, started, http)
    finally:
        repair_task.cancel()  # a confident round 1 discards the repair; cancelling a finished task does nothing


async def run_gate(speaker: str, nbest: list[Hypothesis], phrase_result: list[PhraseMatch], conversation: list[str],
                   settings: GateSettings, provider: str, http: httpx.AsyncClient | None = None) -> GateResult:
    """Runs one turn through the gate; pass a long-lived httpx client so each turn reuses warm connections."""
    if http is not None:
        return await _run(speaker, nbest, phrase_result, conversation, settings, provider, http)
    async with httpx.AsyncClient() as own:
        return await _run(speaker, nbest, phrase_result, conversation, settings, provider, own)


def learn_from_choice(speaker: str, heard: str, nbest: list[str], meant: str, source: str) -> dict:
    """Records what he meant (spec 9.1): source pick, typed or review for corrections, spoken for an unchallenged sentence."""
    return add_pair(speaker, heard, nbest, meant, source)
