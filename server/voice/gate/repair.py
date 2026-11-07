"""Repair: Claude Haiku rebuilds up to 3 sentences from the n-best list and phrase matches (API-NOTES 2)."""

import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, Field, ValidationError

from voice.config import MissingKey, require
from voice.gate.candidates import Hypothesis, PhraseMatch

MESSAGES_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-5-5"
TIMEOUT_S = 1.2
MAX_SENTENCES = 3
MAX_EXAMPLES = 5
RETRY_BACKOFF_S = (0.1, 0.3)
RULES = """Your job in this call is different from judging: you repair speech-recogniser output for this speaker.
You get his recogniser's best hypotheses (labelled h1, h2, ...) with log-probabilities, the saved phrases his audio sounded like (labelled by phrase id), the conversation so far, and past corrections showing what the recogniser heard and what he actually meant.
Return up to 3 sentences he most likely said, most likely first.
- Every sentence must be explainable from at least one hypothesis or phrase match. List the labels it comes from in based_on.
- Fix misheard words. Do not add meaning he did not express, and do not answer or continue the conversation.
- Keep his phrasing and word order where the hypotheses agree on them.
- Use British spelling, normal capitals and punctuation.
- Fewer sentences are fine. Return an empty list if nothing sensible can be built from the evidence."""
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"sentences": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "based_on": {"type": "array", "items": {"type": "string"}}},
        "required": ["text", "based_on"], "additionalProperties": False,
    }}},
    "required": ["sentences"], "additionalProperties": False,
}


@dataclass
class Repair:
    """The repaired sentences, how long the call took, and why it produced none when it failed."""

    sentences: list[str]
    ms: int
    error: str | None = None
    timed_out: bool = False
    usage: dict = field(default_factory=dict)


class RepairError(RuntimeError):
    """The repair call failed; the message says why in plain words."""


class RepairedSentence(BaseModel):
    """One repaired sentence and the hypothesis or phrase labels it comes from."""

    text: str = Field(min_length=1, max_length=300)
    based_on: list[str]


class RepairOutput(BaseModel):
    """The structured output the model must return."""

    sentences: list[RepairedSentence]


def build_request(static_block: str, memory_pairs: list[dict], conversation: list[str],
                  nbest: list[Hypothesis], phrases: list[PhraseMatch]) -> dict:
    """The Messages request: rules plus the static block as a cached system prefix, the turn as JSON."""
    turn = {
        "past_corrections": [{"recogniser_heard": p["heard"], "he_meant": p["meant"]} for p in memory_pairs[:MAX_EXAMPLES]],
        "conversation_so_far": conversation[-6:],
        "hypotheses": [{"label": f"h{i}", "text": h.text, "logprob": round(h.logprob, 3)} for i, h in enumerate(nbest, 1)],
        "phrase_matches": [{"label": m.phrase_id, "text": m.text, "score": round(m.score, 3), "margin": round(m.margin, 3)}
                           for m in phrases],
    }
    return {
        "model": MODEL,
        "max_tokens": 400,
        "system": [{"type": "text", "text": f"{RULES}\n\n{static_block}", "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "messages": [{"role": "user", "content": json.dumps(turn, ensure_ascii=False)}],
        # Low effort and no thinking keep Haiku inside the 1.2 s budget; one fixed setting keeps the cache valid.
        "thinking": {"type": "disabled"},
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    }


async def _post(http: httpx.AsyncClient, body: dict) -> dict:
    """POSTs to Messages; 401/403 names the key, 429/5xx retry twice, anything else fails clearly."""
    headers = {"x-api-key": require("ANTHROPIC_API_KEY", "sentence repair"), "anthropic-version": "2023-06-01"}
    for attempt in range(len(RETRY_BACKOFF_S) + 1):
        response = await http.post(MESSAGES_URL, json=body, headers=headers, timeout=TIMEOUT_S)
        if response.status_code in (401, 403):
            raise RepairError(f"ANTHROPIC_API_KEY is wrong (HTTP {response.status_code}: {response.text[:200]}).")
        if (response.status_code == 429 or response.status_code >= 500) and attempt < len(RETRY_BACKOFF_S):
            await asyncio.sleep(RETRY_BACKOFF_S[attempt])
            continue
        if response.status_code != 200:
            raise RepairError(f"Anthropic Messages failed with HTTP {response.status_code}: {response.text[:200]}.")
        try:
            return response.json()
        except ValueError as exc:
            raise RepairError("Anthropic Messages returned a body that is not JSON.") from exc
    raise RepairError("Anthropic Messages kept failing.")


def parse_output(data: dict, allowed_labels: set[str]) -> list[str]:
    """Validates the model's JSON and keeps up to 3 sentences that cite a real hypothesis or phrase."""
    if data.get("stop_reason") == "refusal":
        raise RepairError("Haiku refused to repair this turn.")
    text = next((block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"), "")
    output = RepairOutput.model_validate_json(text)
    grounded = [s.text.strip() for s in output.sentences if allowed_labels.intersection(s.based_on)]
    return grounded[:MAX_SENTENCES]


async def _repair_once_or_twice(http: httpx.AsyncClient, body: dict, allowed_labels: set[str]) -> tuple[list[str], dict]:
    """Calls Haiku and validates; a malformed answer is retried once while the outer timeout allows."""
    for attempt in range(2):
        data = await _post(http, body)
        try:
            return parse_output(data, allowed_labels), data.get("usage", {})
        except ValidationError as exc:
            if attempt == 1:
                raise RepairError(f"Haiku returned malformed output twice ({exc.errors()[:1]}).") from exc
    return [], {}


async def repair(static_block: str, memory_pairs: list[dict], conversation: list[str], nbest: list[Hypothesis],
                 phrases: list[PhraseMatch], http: httpx.AsyncClient | None = None, timeout_s: float = TIMEOUT_S) -> Repair:
    """Up to 3 repaired sentences within the timeout; on any failure returns none and says why, never raises."""
    started = time.perf_counter()
    body = build_request(static_block, memory_pairs, conversation, nbest, phrases)
    allowed = {f"h{i}" for i in range(1, len(nbest) + 1)} | {m.phrase_id for m in phrases}
    sentences, usage, error, timed_out = [], {}, None, False
    try:
        async with asyncio.timeout(timeout_s):
            if http is None:
                async with httpx.AsyncClient() as own:
                    sentences, usage = await _repair_once_or_twice(own, body, allowed)
            else:
                sentences, usage = await _repair_once_or_twice(http, body, allowed)
    except (TimeoutError, httpx.TimeoutException):
        error, timed_out = f"Repair timed out after {timeout_s} s.", True
    except (RepairError, MissingKey) as exc:
        error = str(exc)
    except httpx.HTTPError as exc:
        error = f"Could not reach Anthropic Messages: {exc}."
    return Repair(sentences, round((time.perf_counter() - started) * 1000), error, timed_out, usage)
