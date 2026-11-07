"""The streamed-voice numbers for the Experiments screen and the R1 acceptance check (EXP-SPEC 2 and 12)."""

from statistics import median

# R1 is accepted on at least this many streamed turns (EXP-SPEC 12).
R1_MIN_TURNS = 20
R1_FIRST_SOUND_MS = 350
# Confident turns should be voiced within this long of the end of speech (EXP-SPEC 2).
R1_VOICED_WITHIN_MS = 1_200
RECENT = 50


def _median(values: list[float]) -> float | None:
    return round(median(values), 1) if values else None


def _decision_to_sound(turn: dict) -> float | None:
    """Phone-measured ms from the result arriving (the decision) to the first sound playing."""
    text, audio = turn.get("ms_end_to_text"), turn.get("ms_end_to_audio")
    return float(audio - text) if isinstance(text, (int, float)) and isinstance(audio, (int, float)) else None


def realtime_report(turns: list[dict]) -> dict:
    """Medians over his last streamed turns, the same for whole-clip turns, and whether R1's target is met."""
    spoken = [t for t in turns if t.get("action") == "speak" and t.get("outcome") == "spoken"]
    streamed = [t for t in turns if (t.get("exp") or {}).get("realtime_voice")][-RECENT:]
    whole = [t for t in spoken if not (t.get("exp") or {}).get("realtime_voice")][-RECENT:]
    first_sound = [v for v in map(_decision_to_sound, streamed) if v is not None]
    confident = [t["ms_end_to_audio"] for t in streamed if t in spoken and isinstance(t.get("ms_end_to_audio"), (int, float))]
    within = sum(1 for ms in confident if ms <= R1_VOICED_WITHIN_MS)
    median_first = _median(first_sound)
    return {
        "streamed_turns": len(first_sound),
        "first_sound_ms_median": median_first,
        "server_first_chunk_ms_median": _median([t["exp"]["realtime_voice"]["first_chunk_ms"] for t in streamed]),
        "confident_voiced_within_1200_ms": f"{within} of {len(confident)}" if confident else None,
        "whole_clip_first_sound_ms_median": _median([v for v in map(_decision_to_sound, whole) if v is not None]),
        "target_ms": R1_FIRST_SOUND_MS,
        "needed_turns": R1_MIN_TURNS,
        "met": len(first_sound) >= R1_MIN_TURNS and median_first is not None and median_first <= R1_FIRST_SOUND_MS,
    }
