"""Checks the CTranslate2 backend's pure parts with literal values: score conversion, token budget, prompt and guards."""

import time

import pytest

from voice.asr.ct2 import PROMPT_TOKENS, hf_logprob, max_length_for, recognition


def test_ct2_score_becomes_the_transformers_length_normalised_logprob():
    # Three text tokens (-0.1, -0.2, -0.3) and the end token (-0.4): CT2 reports -1.0 / 3, transformers -1.0 / 4.
    assert hf_logprob(-1.0 / 3, 3) == pytest.approx(-0.25)
    assert hf_logprob(-2.0, 4) == pytest.approx(-1.6)


def test_conversion_can_reorder_hypotheses_of_different_lengths():
    # CT2 ranks a 5-token text at -0.30 above a 1-token text at -0.32; transformers ranks the short one first.
    assert hf_logprob(-0.30, 5) == pytest.approx(-0.25)
    assert hf_logprob(-0.32, 1) == pytest.approx(-0.16)


def test_token_budget_matches_max_new_tokens():
    assert max_length_for(128) == 256
    assert max_length_for(96) == 192


def test_prompt_is_english_transcribe_without_timestamps():
    from transformers import WhisperTokenizer

    tokenizer = WhisperTokenizer.from_pretrained("openai/whisper-large-v3-turbo")
    assert tokenizer.convert_tokens_to_ids(PROMPT_TOKENS) == [50258, 50259, 50360, 50364]


def test_recognition_drops_everything_when_no_speech_is_likely():
    result = recognition(["Press the pants.", "press the pants"], [-0.1, -0.2], no_speech=0.7, n=5, started=time.perf_counter())
    assert result.hypotheses == [] and result.dropped == ["Press the pants."]
    assert result.no_speech_probability == 0.7


def test_recognition_keeps_support_counts_and_drops_fillers():
    result = recognition(["Press the pants.", "press the pants", "Thank you."], [-0.11111, -0.2, -0.3], no_speech=0.01, n=5, started=time.perf_counter())
    assert [(h.text, h.logprob, h.support) for h in result.hypotheses] == [("Press the pants.", -0.1111, 2)]
    assert result.dropped == ["Thank you."]
