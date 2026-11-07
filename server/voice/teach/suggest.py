"""'Sentences like yours': Haiku writes short everyday sentences in his style to record, never on health."""

import httpx
from pydantic import BaseModel, ValidationError

from voice.config import require
from voice.gate.memory import load_pairs
from voice.phrases.bank import load_bank

MODEL = "claude-haiku-5-5"
URL = "https://api.anthropic.com/v1/messages"
TIMEOUT_S = 20.0
SCHEMA = {"type": "object", "properties": {"sentences": {"type": "array", "items": {"type": "string"}}},
          "required": ["sentences"], "additionalProperties": False}
RULES = (
    "Write {count} short everyday sentences (4 to 12 words) this person might say, in the same style and vocabulary as "
    "his examples: greetings, shops and cafés, travel, home, family, plans, weather, hobbies. British spelling. Never write "
    "about health, illness, medicine, doctors, hospitals, the body or how he speaks. Don't repeat his examples."
)


class Suggestions(BaseModel):
    """Haiku's structured answer."""

    sentences: list[str]


class SuggestError(RuntimeError):
    """Plain-language reason no sentences could be suggested."""


def examples(speaker: str) -> list[str]:
    """His bank phrases and recently confirmed sentences, the style to imitate."""
    confirmed = [pair["meant"] for pair in load_pairs(speaker)][-20:]
    return [phrase.text for phrase in load_bank(speaker)] + confirmed


async def suggest(http: httpx.AsyncClient, speaker: str, count: int = 10) -> list[str]:
    """Asks Haiku for new sentences; raises SuggestError with a plain reason on failure."""
    body = {"model": MODEL, "max_tokens": 800, "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            "system": RULES.format(count=count), "messages": [{"role": "user", "content": "His examples:\n" + "\n".join(examples(speaker))}]}
    headers = {"x-api-key": require("ANTHROPIC_API_KEY", "Sentences like yours"), "anthropic-version": "2023-06-01"}
    try:
        response = await http.post(URL, json=body, headers=headers, timeout=TIMEOUT_S)
    except httpx.HTTPError as error:
        raise SuggestError(f"Couldn't reach the sentence writer: {error}") from error
    if response.status_code in (401, 403):
        raise SuggestError("ANTHROPIC_API_KEY is wrong or not allowed, so new practice sentences can't be written.")
    if response.status_code != 200:
        raise SuggestError(f"The sentence writer failed (HTTP {response.status_code}).")
    try:
        parsed = Suggestions.model_validate_json(response.json()["content"][0]["text"])
    except (ValidationError, KeyError, IndexError, ValueError) as error:
        raise SuggestError("The sentence writer returned something unreadable.") from error
    seen = {text.strip().lower() for text in examples(speaker)}
    return [s.strip() for s in parsed.sentences if s.strip() and s.strip().lower() not in seen][:count]
