"""'Tell the app' (spec 14.4): maps his spoken request onto one change from a fixed allowed list, with Jev's calibrated choice."""

import httpx

from voice.config import optional
from voice.gate.decide import JEV_URL, DecisionError, JevResponse, _post, _validated
from voice.tts.elevenlabs import voices

# Below this probability the request isn't clear enough to propose anything.
MIN_PROBABILITY = 0.5
NONE_OPTION = "None of these: not a settings request"
INSTRUCTIONS = (
    "A speech recogniser heard these guesses of what a user said to his speech app. Which single settings change is he "
    "asking for? Choose 'None of these' if it is not a settings request or none of the options fits."
)


def allowed_changes() -> dict[str, dict]:
    """The only changes he can make by talking: option text -> {key, to, label}."""
    changes = {
        "Make the text bigger": {"key": "text_size", "to": "bigger", "label": "Text size: bigger"},
        "Make the text smaller": {"key": "text_size", "to": "smaller", "label": "Text size: smaller"},
        "Turn high contrast on": {"key": "high_contrast", "to": True, "label": "High contrast: on"},
        "Turn high contrast off": {"key": "high_contrast", "to": False, "label": "High contrast: off"},
        "Turn animations off (reduce motion)": {"key": "reduce_motion", "to": True, "label": "Reduce motion: on"},
        "Turn animations back on": {"key": "reduce_motion", "to": False, "label": "Reduce motion: off"},
        "Speak more slowly": {"key": "speech_rate", "to": "slower", "label": "Voice speed: slower"},
        "Speak faster": {"key": "speech_rate", "to": "faster", "label": "Voice speed: faster"},
        "Always check with me before speaking": {"key": "before_speaking", "to": "check", "label": "Before speaking: let me check first"},
        "Speak straight away without checking": {"key": "before_speaking", "to": "speak", "label": "Before speaking: speak straight away"},
    }
    for voice in voices()["voices"]:
        changes[f"Use the voice called {voice['name']}"] = {"key": "voice_id", "to": voice["id"], "label": f"Voice: {voice['name']}"}
    return changes


async def map_request(http: httpx.AsyncClient, heard: list[str]) -> dict:
    """Returns {changes: [..], probability, model}; changes is empty when the request isn't clear."""
    if not heard:
        return {"changes": [], "probability": 0.0, "model": ""}
    options = allowed_changes()
    criteria = {name: change["label"] for name, change in options.items()} | {NONE_OPTION: "Not a settings request."}
    body = {
        "model": optional("DECIDE_MODEL", "jev-latest"),
        "state": {"recogniser_guesses_best_first": heard[:5]},
        "questions": {"change": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": criteria}},
    }
    parsed = _validated(JevResponse, await _post(http, JEV_URL, "TYPESAFE_API_KEY", body), "jev")
    answer = parsed.answers.get("change")
    if answer is None:
        raise DecisionError("jev answered without the 'change' question.")
    choice, probability = max(answer.probabilities.items(), key=lambda item: item[1])
    if choice not in options or probability < MIN_PROBABILITY:
        return {"changes": [], "probability": round(probability, 3), "model": parsed.model}
    return {"changes": [{**options[choice], "from": None}], "probability": round(probability, 3), "model": parsed.model}
