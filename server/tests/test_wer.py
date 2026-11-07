"""WER and words understood, with literal expected values (spec 15.2)."""

import pytest

from voice.evaluation.wer import clip_wer_percent, normalise, wer_percent, words_understood


def test_one_dropped_word_in_eight_is_12_5_percent():
    assert clip_wer_percent("The birch canoe slid on the smooth planks.", "the birch canoe slid on smooth planks") == 12.5


def test_case_and_punctuation_do_not_count():
    assert clip_wer_percent("Glue the sheet to the dark blue background.", "glue the sheet to the dark blue background") == 0.0


def test_british_and_american_spellings_match():
    assert clip_wer_percent("The colour of the sea.", "the color of the sea") == 0.0


def test_contractions_are_expanded_on_both_sides():
    assert normalise("It's easy to tell the depth of a well.") == normalise("it is easy to tell the depth of a well")


def test_corpus_wer_pools_errors_over_all_reference_words():
    # 1 deletion over 8 words plus 1 substitution over 7 words: 2 errors / 15 words.
    references = ["The birch canoe slid on the smooth planks.", "Rice is often served in round bowls."]
    hypotheses = ["the birch canoe slid on smooth planks", "rice is often served in round balls"]
    assert wer_percent(references, hypotheses) == 13.33


def test_empty_hypothesis_is_all_deletions():
    assert clip_wer_percent("Two blue fish swam in the tank.", "") == 100.0


def test_insertions_can_push_wer_past_100_but_words_understood_stays_at_0():
    wer = clip_wer_percent("Hello.", "hello there my old friend")
    assert wer == 400.0
    assert words_understood(wer) == 0.0


def test_words_understood_is_100_minus_wer():
    assert words_understood(12.5) == 87.5
    assert words_understood(0.0) == 100.0


def test_mismatched_lengths_are_refused():
    with pytest.raises(ValueError):
        wer_percent(["a"], [])
