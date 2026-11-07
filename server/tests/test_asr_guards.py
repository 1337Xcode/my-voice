"""Checks the recogniser's hallucination guards and n-best de-duplication with literal examples."""

from voice.asr.whisper import compression_ratio, distinct, keep_hypothesis


def test_stock_filler_outputs_are_dropped():
    assert not keep_hypothesis("Thank you for watching!")
    assert not keep_hypothesis(" you")
    assert keep_hypothesis("Can I have a flat white, please?")


def test_repetition_loops_are_dropped():
    loop = "the the the the the the the the the the the the the the the the the the the the"
    assert compression_ratio(loop) > 2.4
    assert not keep_hypothesis(loop)


def test_beams_that_differ_only_in_case_or_punctuation_count_once():
    texts = ["Press the pants.", "press the pants", "Press the plants.", "Thank you.", "Press the pans."]
    scores = [-0.1, -0.2, -0.3, -0.4, -0.5]
    kept, dropped = distinct(texts, scores, n=5)
    assert [(text, support) for text, _, support in kept] == [("Press the pants.", 2), ("Press the plants.", 1), ("Press the pans.", 1)]
    assert dropped == ["Thank you."]


def test_distinct_keeps_at_most_n_best_first():
    kept, _ = distinct(["a cat", "a hat", "a bat"], [-0.5, -0.1, -0.3], n=2)
    assert [text for text, _, _ in kept] == ["a hat", "a bat"]
