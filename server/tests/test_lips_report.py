"""The X0 capture-test verdict: 600 s, 99% of seconds at 24 fps or more, no stalls, no mic gaps, 16 kHz mic."""

from voice.lips.report import capture_verdict


def report(**change) -> dict:
    base = {"seconds": 600, "frames": 15_000, "face_frames": 14_700, "fps_per_second": [25] * 600, "stalls": 0, "dropped": 0,
            "mic_frames": 6_000, "mic_gaps": 0, "mic_rate_hz": 16_010.0, "voice_plays": 40}
    return {**base, **change}


def test_ten_steady_minutes_pass():
    verdict = capture_verdict(report())
    assert verdict["met"] is True
    assert (verdict["fps_median"], verdict["fps_lowest"], verdict["seconds_at_24_pct"], verdict["face_visible_pct"]) == (25, 25, 100.0, 98.0)


def test_a_few_slow_seconds_fail_beyond_one_percent():
    assert capture_verdict(report(fps_per_second=[25] * 594 + [20] * 6))["met"] is True  # 99.0%
    assert capture_verdict(report(fps_per_second=[25] * 593 + [20] * 7))["met"] is False


def test_short_runs_stalls_mic_gaps_and_a_changed_mic_rate_fail():
    assert capture_verdict(report(seconds=300, fps_per_second=[25] * 300))["met"] is False
    assert capture_verdict(report(stalls=1))["met"] is False
    assert capture_verdict(report(mic_gaps=2))["met"] is False
    assert capture_verdict(report(mic_rate_hz=48_000.0))["met"] is False
