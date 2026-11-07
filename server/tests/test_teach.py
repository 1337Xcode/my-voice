"""Checks Teach's prompt order (spec 9.5), the phrase test hold-out, and Review verdicts (9.2) on real files."""

import numpy as np
import pytest

from voice.audio.pcm import wav_bytes


@pytest.fixture
def speaker(tmp_path, monkeypatch):
    import voice.config as config
    import voice.storage as storage

    for module in (config, storage):
        monkeypatch.setattr(module, "DATA_ROOT", tmp_path / "data")
        monkeypatch.setattr(module, "MODELS_ROOT", tmp_path / "models")
    return "P1"


def tone(seconds: float = 1.0) -> bytes:
    """A real 220 Hz tone as a WAV upload (signal for the conversion path, not product data)."""
    t = np.arange(int(16_000 * seconds)) / 16_000
    return wav_bytes((0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32))


def test_first_prompt_is_his_first_phrase_as_a_template(speaker):
    from voice.teach.prompts import next_prompt

    prompt = next_prompt(speaker)
    assert prompt == {"kind": "phrase", "text": "My app speaks for me. Thanks for your patience.", "phrase_id": "p01", "split": "train", "condition": "quiet", "progress": {"done": 0, "of": 2}}


def test_second_recording_of_a_phrase_is_held_out_then_the_next_phrase_follows(speaker):
    from voice.phrases.bank import load_bank
    from voice.teach.prompts import next_prompt
    from voice.teach.recording import store_upload

    store_upload(speaker, tone(), ".wav", "My app speaks for me. Thanks for your patience.", "p01", None, "train", "quiet")
    second = next_prompt(speaker)
    assert (second["phrase_id"], second["split"]) == ("p01", "test")
    store_upload(speaker, tone(), ".wav", "My app speaks for me. Thanks for your patience.", "p01", None, "test", "quiet")
    assert next_prompt(speaker)["phrase_id"] == "p02"
    assert len(load_bank(speaker)[0].template_clip_ids) == 1  # the held-out repeat is never a template


def test_onboarding_test_sentence_keeps_its_ta_id_and_test_split(speaker):
    from voice.teach.recording import store_upload

    record = store_upload(speaker, tone(), ".wav", "The birch canoe slid on the smooth planks.", None, "ta01", "train", "quiet")
    assert (record.id, record.split, record.trust) == ("ta01", "test", "read")


def test_too_short_recordings_are_refused_with_a_plain_message(speaker):
    from voice.teach.recording import store_upload

    with pytest.raises(ValueError, match="too short"):
        store_upload(speaker, tone(0.1), ".wav", "Yes, please.", None, None, "train", "quiet")


def test_review_approve_makes_a_turn_trainable_and_reject_excludes_it(speaker):
    from voice.clips.selection import is_trainable
    from voice.teach.recording import apply_review, keep_turn_audio, review_items

    audio = (0.3 * np.sin(np.arange(16_000) / 10)).astype(np.float32)
    keep_turn_audio(speaker, "t-1", audio, "See you later.", "implicit", None)
    keep_turn_audio(speaker, "t-2", audio, "Have a good day.", "implicit", None)
    assert {item["turn_id"] for item in review_items(speaker)} == {"t-1", "t-2"}
    assert is_trainable(apply_review(speaker, "t-1", "approve", None))
    assert apply_review(speaker, "t-2", "reject", None).excluded
    assert review_items(speaker) == []


def test_export_holds_every_file_and_delete_removes_data_and_models(speaker):
    import io
    import zipfile

    from voice.http.data import delete_speaker, zip_speaker
    from voice.storage import models_dir
    from voice.teach.recording import store_upload

    store_upload(speaker, tone(), ".wav", "Yes, please.", None, None, "train", "quiet")
    (models_dir(speaker) / "registry.json").parent.mkdir(parents=True, exist_ok=True)
    (models_dir(speaker) / "registry.json").write_text("{}")
    names = zipfile.ZipFile(io.BytesIO(zip_speaker(speaker))).namelist()
    assert "models/registry.json" in names and "data/clips.jsonl" in names
    assert len(delete_speaker(speaker)) == 2
    assert zipfile.ZipFile(io.BytesIO(zip_speaker(speaker))).namelist() == []
