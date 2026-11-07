"""Compares the gate providers (TypeSafe Jev, OpenAI Decisions) on confusable turns: accuracy, safety and latency.

Run from server/:  uv run --with httpx --with rapidfuzz python scripts_gate_compare.py [--cases cases.json]
A cases file is a JSON list of {"nbest": [[text, logprob], ...], "phrases": [[phrase_id, text, distance, score, margin], ...],
"conversation": ["them: ...", ...], "expected": "the sentence he said" or null when no candidate is right}.
Keys are read from the environment, then from the repo .env; their values are never printed.
"""

import argparse
import asyncio
import json
import os
import statistics
import tempfile
from pathlib import Path

import httpx

import voice.storage as storage
from voice.gate.act import GateSettings, choose_action
from voice.gate.candidates import Hypothesis, PhraseMatch, build_candidates, normalise
from voice.gate.decide import DecisionError, decide
from voice.gate.static_block import build_static_block

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def case(nbest, phrases=(), conversation=(), expected=None) -> dict:
    """One built-in case; logprobs follow rank, as length-normalised Whisper scores do."""
    return {"nbest": nbest, "phrases": list(phrases), "conversation": list(conversation), "expected": expected}


BUILT_IN_CASES = [
    case([["can I have a fat white please", -0.42], ["can I have a flat white please", -0.55], ["can I half a flat way please", -0.91]],
         [["p11", "Can I have a flat white, please?", 0.18, 0.74, 0.31]], ["them: Hi there, what can I get you?"],
         "Can I have a flat white, please?"),
    case([["can I pay by car", -0.38], ["can I play by card", -0.61], ["can I pay by card", -0.66]],
         [["p13", "Can I pay by card?", 0.2, 0.68, 0.27]], ["them: That's four pounds twenty."], "Can I pay by card?"),
    case([["where is the nation please", -0.7], ["wear is the station please", -0.8], ["where is this station please", -0.9]],
         [], [], None),
    case([["no thing you", -0.5], ["no thank you", -0.6], ["now thank you", -0.9]],
         [["p07", "No, thank you.", 0.25, 0.6, 0.2]], ["them: Do you want a receipt?"], "No, thank you."),
    case([["could you speak a bit lower please", -0.45], ["could you seek a bit slower please", -0.6],
          ["good use speak a bit slower please", -0.95]],
         [["p20", "Could you speak a bit slower, please?", 0.3, 0.55, 0.1]], ["them: Hello, you're through to bookings."],
         "Could you speak a bit slower, please?"),
    case([["the bin please", -0.6], ["the pill please", -0.7], ["the bill please", -0.75]],
         [["p17", "The bill, please.", 0.22, 0.66, 0.3]], ["them: Anything else for you today?"], "The bill, please."),
    case([["is it going to rain later", -0.3], ["is it going to train later", -0.5], ["is it doing to rain later", -0.7]],
         [], ["them: It's very grey out there."], "is it going to rain later"),
    case([["the cow sat on the gate", -1.8], ["they sow sad on a cake", -1.9], ["a cat sat on the gate", -2.0]], [], [], None),
    case([["I'll massage you", -0.5], ["aisle message you", -0.8], ["I'll message you", -0.85]],
         [["p33", "I'll message you.", 0.3, 0.5, 0.15]], ["them: Let me know when you're home."], "I'll message you."),
    case([["what time do you hope in", -0.7], ["what time do you open", -0.75], ["what time to you open", -0.9]],
         [["p25", "What time do you open?", 0.28, 0.6, 0.22]], ["them: Hello, how can I help?"], "What time do you open?"),
    case([["a return ticket please", -0.35], ["are return tick it please", -0.9], ["a retain ticket please", -1.0]],
         [["p27", "A return ticket, please.", 0.15, 0.8, 0.5]], ["them: Single or return?"], "A return ticket, please."),
    case([["can you tell me please", -0.5], ["can you help me please", -0.55], ["can you sell me please", -0.8]],
         [["p29", "Can you help me, please?", 0.4, 0.45, 0.05]], [], "Can you help me, please?"),
]


def load_env() -> None:
    """Copies repo .env values into the environment for keys that are not already set."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


async def score_case(provider: str, static_block: str, item: dict, http: httpx.AsyncClient) -> dict:
    """Runs one case through one provider and judges the top choice and the action."""
    nbest = [Hypothesis(text, logprob) for text, logprob in item["nbest"]]
    phrases = [PhraseMatch(*match) for match in item["phrases"]]
    candidates = build_candidates(nbest, phrases, [])
    expected = normalise(item["expected"]) if item["expected"] else None
    try:
        decision = await decide(provider, static_block, item["conversation"], candidates, http)
    except DecisionError as exc:
        return {"error": str(exc)}
    action = choose_action(decision.probabilities, GateSettings())
    texts = {c.id: normalise(c.text) for c in candidates}
    top = max((k for k in decision.probabilities if k != "none"), key=decision.probabilities.get)
    return {"ms": decision.ms, "action": action.kind, "top_right": texts[top] == expected if expected else None,
            "wrong_spoken": action.kind == "speak" and texts[action.ids[0]] != expected,
            "right_offered": bool(expected) and expected in [texts[i] for i in action.ids if action.kind != "again"]}


def summarise(provider: str, rows: list[dict]) -> str:
    """One report block per provider."""
    ok = [r for r in rows if "error" not in r]
    errors = [r["error"] for r in rows if "error" in r]
    if not ok:
        return f"{provider}: every call failed, first error: {errors[0] if errors else 'none'}"
    judged = [r for r in ok if r["top_right"] is not None]
    ms = sorted(r["ms"] for r in ok)
    actions = {kind: sum(r["action"] == kind for r in ok) for kind in ("speak", "pick", "again")}
    return (f"{provider}: top choice right {sum(r['top_right'] for r in judged)}/{len(judged)}, "
            f"right sentence spoken or offered {sum(r['right_offered'] for r in judged)}/{len(judged)}, "
            f"wrong sentences spoken {sum(r['wrong_spoken'] for r in ok)}/{len(ok)}, actions {actions}, "
            f"latency median {statistics.median(ms)} ms, p95 {ms[int(0.95 * (len(ms) - 1))]} ms, max {ms[-1]} ms"
            + (f", {len(errors)} errors (first: {errors[0]})" if errors else ""))


async def run(speaker: str, providers: list[str], cases: list[dict], repeat: int) -> None:
    """Runs every case through every provider on one warm connection per provider and prints the summary."""
    static_block = build_static_block(speaker)
    for provider in providers:
        async with httpx.AsyncClient() as http:
            rows = [await score_case(provider, static_block, item, http) for _ in range(repeat) for item in cases]
        print(summarise(provider, rows))


def main() -> None:
    """Parses the arguments, points storage at a scratch folder unless given his data, and runs the comparison."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, help="JSON file of cases (default: the built-in confusable set)")
    parser.add_argument("--providers", default="jev,openai")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--speaker", default="P1")
    parser.add_argument("--data-root", type=Path, help="a copy of speech-data, for his phrase bank and vocabulary")
    parser.add_argument("--openai-base-url", help="overrides OPENAI_BASE_URL for this run")
    args = parser.parse_args()
    load_env()
    if args.openai_base_url:
        os.environ["OPENAI_BASE_URL"] = args.openai_base_url
    storage.DATA_ROOT = args.data_root or Path(tempfile.mkdtemp(prefix="gate-compare-"))
    cases = json.loads(args.cases.read_text(encoding="utf-8")) if args.cases else BUILT_IN_CASES
    asyncio.run(run(args.speaker, args.providers.split(","), cases, args.repeat))


if __name__ == "__main__":
    main()
