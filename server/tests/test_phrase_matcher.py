"""Tests for the phrase matcher's maths: DTW, threshold learning, scores, margins and leave-one-out."""

import math

import numpy as np
import pytest
import torch

from voice.phrases.dtw import dtw_batch
from voice.phrases.matcher import (
    DEFAULT_THRESHOLD,
    learn_threshold,
    loo_report,
    phrase_min_distances,
    rank_phrases,
)


def _basis(*axes: int, dim: int = 4) -> torch.Tensor:
    """Unit vectors along the given axes, as a [T, dim] frame sequence."""
    return torch.eye(dim)[list(axes)]


def _distance(a: torch.Tensor, b: torch.Tensor) -> float:
    """DTW distance of one pair through the batched implementation."""
    lens_a, lens_b = torch.tensor([len(a)]), torch.tensor([len(b)])
    return float(dtw_batch(a[None], lens_a, b[None], lens_b)[0])


def _reference_dtw(a: np.ndarray, b: np.ndarray, band_ratio: float = 0.2) -> float:
    """Slow loop version of the same DP (same band, steps and tie order) used to check the vectorised one."""
    n, m = len(a), len(b)
    slope = (m - 1) / max(n - 1, 1)
    steepest = max(slope, 1 / max(slope, 1e-3))
    half = min(max(math.ceil(band_ratio * max(n, m)), math.ceil(steepest) + 1), max(n, m))
    cost = 1.0 - a @ b.T
    best = {(0, 0): (cost[0, 0], 1)}
    for i in range(n):
        for j in range(m):
            if (i, j) == (0, 0) or abs(j - i * slope) > half:
                continue
            options = [best[p] for p in ((i - 1, j - 1), (i, j - 1), (i - 1, j)) if p in best]
            if options:
                total, length = min(options, key=lambda o: o[0])
                best[(i, j)] = (total + cost[i, j], length + 1)
    total, length = best[(n - 1, m - 1)]
    return total / length


def test_identical_sequences_have_zero_distance():
    seq = _basis(0, 1, 2, 3)
    assert _distance(seq, seq) == pytest.approx(0.0, abs=1e-6)


def test_time_stretched_copy_has_zero_distance():
    # b repeats frames of a, which warping absorbs completely.
    assert _distance(_basis(0, 1, 2), _basis(0, 0, 1, 2, 2)) == pytest.approx(0.0, abs=1e-6)


def test_orthogonal_sequences_have_distance_one():
    assert _distance(_basis(0, 0, 0), _basis(1, 1, 1)) == pytest.approx(1.0, abs=1e-6)


def test_opposite_frames_have_distance_two():
    a = torch.tensor([[1.0, 0.0], [1.0, 0.0]])
    assert _distance(a, -a) == pytest.approx(2.0, abs=1e-6)


def test_cost_is_averaged_over_path_length():
    # a=[e0,e1,e2], b=[e0,e1,e3]: the diagonal path costs 0+0+1 over 3 steps.
    assert _distance(_basis(0, 1, 2), _basis(0, 1, 3)) == pytest.approx(1 / 3, abs=1e-6)


def test_batch_matches_loop_reference_with_padding_and_different_lengths():
    rng = np.random.default_rng(0)
    lengths_a, lengths_b = [7, 12, 5, 9], [10, 6, 5, 20]
    seqs_a = [rng.normal(size=(n, 8)).astype(np.float32) for n in lengths_a]
    seqs_b = [rng.normal(size=(m, 8)).astype(np.float32) for m in lengths_b]
    seqs_a = [s / np.linalg.norm(s, axis=1, keepdims=True) for s in seqs_a]
    seqs_b = [s / np.linalg.norm(s, axis=1, keepdims=True) for s in seqs_b]
    pad = torch.nn.utils.rnn.pad_sequence
    got = dtw_batch(
        pad([torch.from_numpy(s) for s in seqs_a], batch_first=True), torch.tensor(lengths_a),
        pad([torch.from_numpy(s) for s in seqs_b], batch_first=True), torch.tensor(lengths_b),
    )
    expected = [_reference_dtw(a, b) for a, b in zip(seqs_a, seqs_b)]
    assert got.tolist() == pytest.approx(expected, abs=1e-5)


def test_very_different_lengths_still_reach_the_corner():
    assert math.isfinite(_distance(_basis(0, 1), torch.eye(4)[[0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1]]))


def test_default_threshold_used_until_five_pairs():
    cal = learn_threshold([0.1, 0.2, 0.3, 0.4])
    assert (cal.source, cal.threshold, cal.n_pairs) == ("default", DEFAULT_THRESHOLD, 4)


def test_threshold_is_95th_percentile_of_within_distances():
    cal = learn_threshold([0.10, 0.20, 0.30, 0.40, 0.50])
    assert cal.source == "learned"
    assert cal.threshold == pytest.approx(0.48)  # numpy linear interpolation: 0.4 + 0.8 * 0.1 -> 0.48
    assert cal.temperature == pytest.approx(0.48 - 0.30)


def test_phrase_distance_is_closest_template():
    owner = np.array([0, 0, 1, 2, 2])
    got = phrase_min_distances(np.array([0.5, 0.3, 0.4, 0.9, 0.2]), owner, 4)
    assert got[:3].tolist() == [0.3, 0.4, 0.2]
    assert math.isinf(got[3])


def test_ranking_gives_top_three_with_scores_and_margins():
    distances = np.array([0.50, 0.20, 0.30, 0.90])
    ids, texts = ["a", "b", "c", "d"], ["A", "B", "C", "D"]
    top = rank_phrases(distances, ids, texts, temperature=0.1, threshold=0.6)
    assert [m.phrase_id for m in top] == ["b", "c", "a"]
    assert top[0].margin == pytest.approx(0.10)
    assert top[2].margin == pytest.approx(0.40)  # to the 4th phrase
    weights = np.exp(-distances / 0.1)
    assert top[0].score == pytest.approx(weights[1] / weights.sum())
    assert sum(m.score for m in top) < 1.0  # the fourth phrase keeps its share


def test_single_phrase_margin_is_room_under_threshold():
    top = rank_phrases(np.array([0.25]), ["a"], ["A"], temperature=0.1, threshold=0.55)
    assert len(top) == 1 and top[0].score == pytest.approx(1.0)
    assert top[0].margin == pytest.approx(0.30)


def test_phrase_without_templates_is_never_ranked():
    top = rank_phrases(np.array([np.inf, 0.4]), ["a", "b"], ["A", "B"], temperature=0.1, threshold=0.6)
    assert [m.phrase_id for m in top] == ["b"]
    assert rank_phrases(np.array([np.inf]), ["a"], ["A"], 0.1, 0.6) == []


def test_leave_one_out_counts_hits_rejects_and_orphans():
    # Templates 0,1 are phrase p; 2,3 are phrase q; 4 is phrase r with a single recording.
    owner = np.array([0, 0, 1, 1, 2])
    m = np.full((5, 5), 0.9)
    m[0, 1] = m[1, 0] = 0.1
    m[2, 3] = m[3, 2] = 0.2
    np.fill_diagonal(m, 0.0)
    report = loo_report(m, owner, ["p", "q", "r"], ["P", "Q", "R"])
    assert report["n"] == 4
    assert report["accuracy"] == 1.0 and report["reject_rate"] == 0.0
    assert report["n_orphans"] == 1 and report["orphan_reject_rate"] == 1.0  # 0.9 > default 0.55
    assert report["per_phrase"]["p"] == {"n": 2, "correct": 2, "accuracy": 1.0}


def test_leave_one_out_rejection_counts_as_wrong():
    owner = np.array([0, 0])
    m = np.array([[0.0, 0.8], [0.8, 0.0]])  # genuine repeats farther apart than the default threshold
    report = loo_report(m, owner, ["p"], ["P"])
    assert (report["n"], report["accuracy"], report["reject_rate"]) == (2, 0.0, 1.0)
