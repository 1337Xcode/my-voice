"""Checks gate calibration (spec 15.4) with literal replay results."""

from voice.evaluation.pipeline_eval import choose_threshold, curve


def rows(*pairs):
    return [{"top_p": p, "top_wer": wer} for p, wer in pairs]


def test_curve_counts_wrong_spoken_turns_and_asks_per_threshold():
    replay = rows((0.99, 0.0), (0.90, 0.0), (0.70, 25.0), (0.60, 0.0))
    points = {p["threshold"]: p for p in curve(replay)}
    assert points[0.6] == {"threshold": 0.6, "spoken": 4, "wrong_spoken_rate": 0.25, "ask_rate": 0.0}
    assert points[0.72] == {"threshold": 0.72, "spoken": 2, "wrong_spoken_rate": 0.0, "ask_rate": 0.5}


def test_threshold_is_the_lowest_with_under_two_percent_wrong():
    replay = rows((0.99, 0.0), (0.90, 0.0), (0.70, 25.0), (0.60, 0.0))
    assert choose_threshold(curve(replay)) == 0.72


def test_a_wrong_sentence_at_high_confidence_pushes_the_threshold_to_the_top():
    assert choose_threshold(curve(rows((0.99, 50.0), (0.5, 0.0)))) == 0.98


def test_threshold_is_applied_only_with_enough_replayed_clips():
    from voice.evaluation.pipeline_eval import calibrated_threshold

    assert calibrated_threshold({"jev": {"speak_threshold": 0.8, "n": 34}}, "jev") == 0.8
    assert calibrated_threshold({"jev": {"speak_threshold": 0.6, "n": 5}}, "jev") is None
    assert calibrated_threshold({"jev": {"speak_threshold": 0.8, "n": 34}}, "openai") is None
