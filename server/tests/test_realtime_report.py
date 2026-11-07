"""The streamed-voice report (EXP R1): which turns count, the medians, and the 20-turn, 350 ms acceptance rule."""

from voice.realtime.report import realtime_report


def streamed(text_ms: int, audio_ms: int, first_chunk_ms: float = 120.0) -> dict:
    return {"action": "speak", "outcome": "spoken", "ms_end_to_text": text_ms, "ms_end_to_audio": audio_ms,
            "exp": {"realtime_voice": {"first_chunk_ms": first_chunk_ms}}}


def whole_clip(text_ms: int, audio_ms: int) -> dict:
    return {"action": "speak", "outcome": "spoken", "ms_end_to_text": text_ms, "ms_end_to_audio": audio_ms, "exp": {}}


def test_medians_split_streamed_and_whole_clip_turns():
    turns = [streamed(800, 1000), streamed(900, 1200), streamed(700, 1100), whole_clip(800, 1700), whole_clip(800, 1500)]
    report = realtime_report(turns)
    assert report["streamed_turns"] == 3
    assert report["first_sound_ms_median"] == 300.0  # 200, 300, 400
    assert report["whole_clip_first_sound_ms_median"] == 800.0  # 900, 700
    assert report["confident_voiced_within_1200_ms"] == "3 of 3"
    assert report["met"] is False  # fewer than 20 turns


def test_twenty_fast_turns_meet_the_target():
    report = realtime_report([streamed(800, 1100)] * 20)
    assert report["first_sound_ms_median"] == 300.0
    assert report["met"] is True


def test_slow_streaming_does_not_meet_the_target():
    report = realtime_report([streamed(800, 1200)] * 25)
    assert report["first_sound_ms_median"] == 400.0
    assert report["met"] is False


def test_turns_without_phone_timing_are_not_counted():
    turn = streamed(800, 1000)
    turn["ms_end_to_audio"] = None
    assert realtime_report([turn])["streamed_turns"] == 0
