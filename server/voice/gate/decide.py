"""The decision gate: asks TypeSafe Jev or OpenAI Decisions which candidate he said (spec 8.6, API-NOTES 1 and 6)."""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from voice.config import optional, require
from voice.gate.candidates import Candidate, describe, features

PROVIDERS = ("jev", "openai")
NONE_ID = "none"
INSTRUCTIONS = (
    "Which sentence did this speaker most likely say? Weigh recogniser agreement and scores, phrase-match strength, "
    "whether it fits the conversation, and his known phrases. Choose none if no candidate is likely."
)
NONE_DESCRIPTION = "He said something else: no candidate is likely."
JEV_URL = "https://api.typesafe.ai/v1/systemone"
CONVERSATION_TURNS = 6
# Latency budget: round 1 normally answers in 150 to 400 ms. One attempt may take at most 1.5 s, and all attempts
# together at most 2.0 s, so a 429/5xx is retried (twice, 100 then 300 ms apart) only while that budget lasts.
# A timeout is never retried: it has already spent the budget.
ATTEMPT_TIMEOUT_S = 1.5
TOTAL_BUDGET_S = 2.0
RETRY_BACKOFF_S = (0.1, 0.3)


@dataclass
class Decision:
    """One gate answer: probability per candidate id (and 'none'), with who answered and how fast."""

    probabilities: dict[str, float]
    confidence: float | None
    provider: str
    model: str
    ms: int
    raw_usage: dict = field(default_factory=dict)


class DecisionError(RuntimeError):
    """The gate could not answer; the message says why in plain words."""


class JevAnswer(BaseModel):
    """A TypeSafe choice answer; probabilities are keyed by option name."""

    type: Literal["choice"]
    choice: str
    confidence: float | None = None
    probabilities: dict[str, float]


class JevResponse(BaseModel):
    """The TypeSafe /v1/systemone response."""

    model: str
    answers: dict[str, JevAnswer]
    usage: dict = {}


class OpenAIProbability(BaseModel):
    """One entry of an OpenAI Decisions probabilities array."""

    value: str
    probability: float


class OpenAIAnswer(BaseModel):
    """An OpenAI Decisions answer; a refusal carries only type and name."""

    type: str
    name: str
    choice: str | None = None
    probabilities: list[OpenAIProbability] = []
    confidence: float | None = None


class OpenAIResponse(BaseModel):
    """The OpenAI /v1/decisions response."""

    model: str
    answers: list[OpenAIAnswer]
    usage: dict = {}


def _error_message(response: httpx.Response) -> str:
    """The provider's own error message, or the start of the body."""
    try:
        error = response.json().get("error")
        return error.get("message", str(error)) if isinstance(error, dict) else str(error or response.text[:300])
    except (ValueError, AttributeError):
        return response.text[:300]


async def _post(http: httpx.AsyncClient, url: str, key_variable: str, body: dict) -> dict:
    """POSTs within the latency budget above; maps auth, rate-limit and server errors to DecisionError."""
    headers = {"Authorization": f"Bearer {require(key_variable, 'the decision gate')}"}
    deadline = time.monotonic() + TOTAL_BUDGET_S
    for attempt in range(len(RETRY_BACKOFF_S) + 1):
        timeout = min(ATTEMPT_TIMEOUT_S, deadline - time.monotonic())
        try:
            response = await http.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise DecisionError(f"{url} did not answer within {timeout:.1f} s.") from exc
        except httpx.HTTPError as exc:
            raise DecisionError(f"Could not reach {url}: {exc}.") from exc
        if response.status_code in (401, 403):
            raise DecisionError(
                f"{key_variable} is wrong or not allowed here (HTTP {response.status_code}: {_error_message(response)})."
            )
        retryable = response.status_code == 429 or response.status_code >= 500
        if retryable and attempt < len(RETRY_BACKOFF_S) and deadline - time.monotonic() > RETRY_BACKOFF_S[attempt] + 0.2:
            await asyncio.sleep(RETRY_BACKOFF_S[attempt])
            continue
        if response.status_code != 200:
            raise DecisionError(f"{url} failed with HTTP {response.status_code}: {_error_message(response)}.")
        try:
            return response.json()
        except ValueError as exc:
            raise DecisionError(f"{url} returned a body that is not JSON.") from exc
    raise DecisionError(f"{url} kept failing.")


def _validated(model: type[BaseModel], data: dict, provider: str):
    """Parses a provider response, or raises DecisionError describing the mismatch."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise DecisionError(f"{provider} returned an unexpected answer shape: {exc.errors()[:2]}.") from exc


def _probabilities(by_id: dict[str, float], candidates: list[Candidate]) -> dict[str, float]:
    """One probability per candidate id plus 'none'; options the provider left out get 0."""
    return {key: float(by_id.get(key, 0.0)) for key in [c.id for c in candidates] + [NONE_ID]}


async def _decide_jev(http: httpx.AsyncClient, static_block: str, conversation: list[str],
                      candidates: list[Candidate]) -> tuple:
    """Jev sees option names, so the options are the sentences themselves, with their evidence as descriptions."""
    by_name = {c.text: c.id for c in candidates}
    none_option = "None of these sentences" if "None of these" in by_name else "None of these"
    criteria = {c.text: describe(c) for c in candidates} | {none_option: NONE_DESCRIPTION}
    body = {
        "model": optional("DECIDE_MODEL", "jev-latest"),
        "state": {"about_the_speaker": static_block, "conversation_so_far": conversation[-CONVERSATION_TURNS:],
                  "candidates": [features(c) for c in candidates]},
        "questions": {"meant": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": criteria}},
    }
    parsed = _validated(JevResponse, await _post(http, JEV_URL, "TYPESAFE_API_KEY", body), "jev")
    answer = parsed.answers.get("meant")
    if answer is None:
        raise DecisionError("jev answered without the 'meant' question.")
    by_id = {NONE_ID if name == none_option else by_name.get(name, ""): p for name, p in answer.probabilities.items()}
    return by_id, answer.confidence, parsed.model, parsed.usage


async def _decide_openai(http: httpx.AsyncClient, static_block: str, conversation: list[str],
                         candidates: list[Candidate]) -> tuple:
    """Only the static block goes in the input, so its 1,024+ token prefix caches; volatile parts go in the question."""
    base_url = optional("OPENAI_BASE_URL", "https://eu.api.openai.com/v1").rstrip("/")
    volatile = {"conversation_so_far": conversation[-CONVERSATION_TURNS:],
                "candidates": [{"id": c.id, **features(c), "evidence": describe(c)} for c in candidates]}
    choices = [{"value": c.id, "description": c.text} for c in candidates]
    body = {
        "model": optional("PARSE_MODEL", "gpt-6-luna"),
        "input": [{"role": "developer", "content": [{"type": "input_text", "text": static_block}]}],
        "prompt_cache_key": "gate-" + hashlib.sha256(static_block.encode()).hexdigest()[:16],
        "questions": [{
            "type": "choice", "name": "meant",
            "instructions": [{"type": "input_text", "text": INSTRUCTIONS}, {"type": "input_json", "data": volatile}],
            "choices": choices + [{"value": NONE_ID, "description": NONE_DESCRIPTION}],
        }],
    }
    parsed = _validated(OpenAIResponse, await _post(http, f"{base_url}/decisions", "OPENAI_API_KEY", body), "openai")
    answer = next((a for a in parsed.answers if a.name == "meant"), None)
    if answer is None or answer.type != "choice":
        raise DecisionError(f"openai did not answer the question ({answer.type if answer else 'no answer'}).")
    by_id = {p.value: p.probability for p in answer.probabilities}
    return by_id, answer.confidence, parsed.model, parsed.usage


async def decide(provider: str, static_block: str, conversation: list[str], candidates: list[Candidate],
                 http: httpx.AsyncClient | None = None) -> Decision:
    """Asks the chosen provider which candidate he said; pass a long-lived client to reuse its connection."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown gate provider {provider!r}; expected one of {', '.join(PROVIDERS)}.")
    if not candidates:
        raise ValueError("The gate needs at least one candidate.")
    call = _decide_jev if provider == "jev" else _decide_openai
    started = time.perf_counter()
    if http is None:
        async with httpx.AsyncClient() as own:
            by_id, confidence, model, usage = await call(own, static_block, conversation, candidates)
    else:
        by_id, confidence, model, usage = await call(http, static_block, conversation, candidates)
    ms = round((time.perf_counter() - started) * 1000)
    return Decision(_probabilities(by_id, candidates), confidence, provider, model, ms, usage)
