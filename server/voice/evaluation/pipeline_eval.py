"""eval_pipeline (spec 15.4): replays every test clip through the whole turn and calibrates the speak threshold."""

import asyncio
import time

import httpx

from voice.audio.pcm import read_audio
from voice.clips.selection import condition_audio, load_frozen_test_set
from voice.evaluation.wer import clip_wer_percent
from voice.gate.act import GateSettings
from voice.gate.candidates import Hypothesis, PhraseMatch
from voice.gate.pipeline import run_gate
from voice.storage import read_json, speaker_dir, write_json

# A spoken sentence counts as wrong when its WER against the reference is over 10% (spec 15.4).
WRONG_WER = 10.0
MAX_WRONG_SPOKEN = 0.02
THRESHOLDS = [round(0.50 + 0.02 * step, 2) for step in range(25)]  # 0.50 .. 0.98
# Forces round 2 on every clip so the curve sees the final probabilities whatever the threshold.
NEVER_CONFIDENT = GateSettings(speak_threshold=1.01, pick_threshold=0.0)


async def replay_clip(whisper, matchers, speaker: str, audio, reference: str, provider: str, http) -> dict:
    """One clip through recognisers and gate with no conversation; returns the top candidate and its probability."""
    recognition = await asyncio.to_thread(whisper.nbest, audio)
    phrase = await asyncio.to_thread(matchers.match, speaker, audio) if matchers else None
    nbest = [Hypothesis(h.text, h.logprob, h.support) for h in recognition.hypotheses]
    phrases = [PhraseMatch(m.phrase_id, m.text, m.distance, m.score, m.margin) for m in (phrase.matches if phrase else [])]
    gate = await run_gate(speaker, nbest, phrases, [], NEVER_CONFIDENT, provider, http)
    top = gate.candidates[0] if gate.candidates else None
    top3 = sum((c.p or 0.0) for c in gate.candidates[:3])
    text = top.text if top else ""
    return {"reference": reference, "top_text": text, "top_p": (top.p or 0.0) if top else 0.0, "top3_p": top3,
            "top_wer": clip_wer_percent(reference, text) if text else 100.0, "errors": gate.errors,
            "in_top3": any(clip_wer_percent(reference, c.text) <= WRONG_WER for c in gate.candidates[:3])}


def curve(rows: list[dict]) -> list[dict]:
    """Wrong-but-spoken rate (of spoken turns) and ask rate for each threshold."""
    points = []
    for threshold in THRESHOLDS:
        spoken = [r for r in rows if r["top_p"] >= threshold]
        wrong = sum(r["top_wer"] > WRONG_WER for r in spoken)
        points.append({"threshold": threshold, "spoken": len(spoken), "wrong_spoken_rate": round(wrong / len(spoken), 4) if spoken else 0.0,
                       "ask_rate": round(1 - len(spoken) / len(rows), 4) if rows else 0.0})
    return points


def choose_threshold(points: list[dict]) -> float:
    """The lowest threshold whose wrong-but-spoken rate is under 2%; the highest one tested if none is."""
    passing = [p["threshold"] for p in points if p["wrong_spoken_rate"] < MAX_WRONG_SPOKEN]
    return min(passing) if passing else THRESHOLDS[-1]


# Fewer replayed clips than this and the curve is too coarse to move his live threshold.
MIN_CLIPS_TO_APPLY = 20


def apply_threshold(speaker: str, summary: dict) -> float | None:
    """Sets his live speak_threshold to the calibrated value for the gate provider he uses (spec 15.4)."""
    settings_path = speaker_dir(speaker) / "settings.json"
    settings = read_json(settings_path, {})
    result = summary["providers"].get(settings.get("decide_provider", "jev"))
    if not result or result["n"] < MIN_CLIPS_TO_APPLY:
        return None
    write_json(settings_path, {**settings, "speak_threshold": result["speak_threshold"]})
    return result["speak_threshold"]


async def eval_pipeline(whisper, matchers, speaker: str, providers: list[str]) -> dict:
    """Replays the frozen test set per gate provider, stores curves and per-clip results, and returns the summary."""
    frozen = load_frozen_test_set(speaker)
    if frozen is None:
        raise FileNotFoundError(f"{speaker} has no frozen test set yet.")
    clips = [(condition, clip_id) for condition, ids in frozen.conditions.items() for clip_id in ids]
    summary = {"test_set": frozen.id, "evaluated_at": round(time.time(), 3), "providers": {}}
    async with httpx.AsyncClient() as http:
        for provider in providers:
            rows = []
            for condition, clip_id in clips:
                audio = read_audio(condition_audio(speaker, condition, clip_id))
                row = await replay_clip(whisper, matchers, speaker, audio, frozen.texts[clip_id], provider, http)
                rows.append({"id": clip_id, "condition": condition, **row})
            points = curve(rows)
            summary["providers"][provider] = {"curve": points, "speak_threshold": choose_threshold(points), "n": len(rows),
                                              "top3_contains_right": round(sum(r["in_top3"] for r in rows) / max(1, len(rows)), 4),
                                              "errors": sum(bool(r["errors"]) for r in rows), "per_clip": rows}
    write_json(speaker_dir(speaker) / "eval" / "pipeline_results.json", summary)
    apply_threshold(speaker, summary)
    return {p: {k: v for k, v in result.items() if k != "per_clip"} for p, result in summary["providers"].items()}
