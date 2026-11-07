"""Promotion rule, registry naming, babble mixing at a set SNR, speed change, and the Harvard lists."""

import numpy as np
import pytest

from voice.training.augment import change_speed
from voice.training.babble import mix_at_snr
from voice.training.prompts import fetch_harvard, harvard_prompts
from voice.training.registry import model_name, next_version, should_promote


def scores(mean: float, quiet: float) -> dict:
    return {"mean_wer": mean, "metrics": {"quiet": {"wer": quiet}}}


def test_half_a_point_better_on_the_mean_promotes():
    assert should_promote(scores(30.0, 20.0), scores(30.5, 20.0))[0] is True


def test_less_than_half_a_point_better_does_not_promote():
    promote, reason = should_promote(scores(30.1, 20.0), scores(30.5, 20.0))
    assert promote is False and "0.5 points lower" in reason


def test_quiet_more_than_a_point_worse_blocks_promotion_even_with_a_better_mean():
    assert should_promote(scores(25.0, 21.5), scores(30.0, 20.0))[0] is False


def test_quiet_exactly_a_point_worse_is_allowed():
    assert should_promote(scores(25.0, 21.0), scores(30.0, 20.0))[0] is True


def test_model_names_follow_the_team_contract():
    assert model_name("S1", 3) == "s1-whisper-lora-v3"


def test_versions_count_up_from_one():
    assert next_version({"versions": {}}) == 1
    assert next_version({"versions": {"p1-whisper-lora-v1": {"version": 1}, "p1-whisper-lora-v2": {"version": 2}}}) == 3


@pytest.mark.parametrize("snr_db", [0.0, 5.0, 15.0])
def test_babble_is_mixed_at_the_requested_snr(snr_db):
    rng = np.random.default_rng(1)
    speech = (0.1 * np.sin(np.arange(16_000) * 0.05)).astype(np.float32)
    noise = (0.2 * rng.standard_normal(16_000)).astype(np.float32)
    mixed = mix_at_snr(speech, noise, snr_db)
    added = mixed - speech
    assert 10 * np.log10(np.mean(speech**2) / np.mean(added**2)) == pytest.approx(snr_db, abs=0.01)


def test_a_loud_mix_is_scaled_down_rather_than_clipped():
    speech = np.full(1000, 0.9, dtype=np.float32)
    assert np.max(np.abs(mix_at_snr(speech, np.full(1000, 0.9, dtype=np.float32), 0.0))) <= 0.99


def test_speed_change_shortens_or_lengthens_the_clip():
    audio = np.zeros(16_000, dtype=np.float32)
    assert len(change_speed(audio, 1.1)) == 14_545
    assert len(change_speed(audio, 0.9)) == 17_778
    assert len(change_speed(audio, 1.0)) == 16_000


def test_skipped_sentences_are_left_out_and_ids_keep_their_place():
    lists = [["Test."], ["Two one.", "Two two."], ["Three one."], ["Four one."], ["Five one.", "Five two.", "Five three.", "Five four."]]
    prompts = harvard_prompts(lists)
    assert [item["id"] for item in prompts["teach"] if item["list"] == 5] == ["h05-01", "h05-02", "h05-04"]
    assert prompts["lists"][4] == ["Five one.", "Five two.", "Five four."]


@pytest.mark.live
def test_harvard_lists_are_fetched_and_list_one_is_the_test_set():
    prompts = harvard_prompts(fetch_harvard())
    assert len(prompts["lists"]) == 72
    assert prompts["test"][0] == {"id": "ta01", "text": "The birch canoe slid on the smooth planks."}
    assert prompts["test"][9]["text"] == "A large size in stockings is hard to sell."
    assert len(prompts["teach"]) == 697 and prompts["teach"][0]["list"] == 2
