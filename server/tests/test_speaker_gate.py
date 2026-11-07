"""Checks the speaker gate's threshold rule (spec 8.3) with literal scores."""

from voice.speaker.gate import cosine, threshold_from_self_scores


def test_threshold_rejects_at_most_one_percent_of_his_own_scores():
    scores = [0.80 + i * 0.001 for i in range(200)]  # 0.800 .. 0.999
    threshold = threshold_from_self_scores(scores)
    rejected = sum(score < threshold for score in scores)
    assert rejected <= 2 and threshold < 0.80


def test_cosine_of_identical_and_opposite_vectors():
    import numpy as np

    v = np.array([1.0, 2.0, 3.0])
    assert round(cosine(v, v), 6) == 1.0 and round(cosine(v, -v), 6) == -1.0
