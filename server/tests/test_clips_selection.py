"""Trainable-clip rules, the validation hold-out (9.3), the frozen test set and the overlap check (15.1)."""

import pytest

from voice.clips.records import ClipRecord, load_clips, save_clip
from voice.clips.selection import (
    OverlapError,
    freeze_test_set,
    is_trainable,
    split_validation,
    trainable_clips,
)


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    import voice.storage as storage

    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(storage, "MODELS_ROOT", tmp_path / "models")
    return tmp_path / "data"


def clip(clip_id: str, **fields) -> ClipRecord:
    return ClipRecord(**{"id": clip_id, "speaker": "P1", "text": f"Sentence {clip_id}.", **fields})


def test_team_yes_and_no_become_booleans():
    assert clip("P1_r001", ok="yes").ok is True
    assert clip("P1_r002", ok="no").ok is False


@pytest.mark.parametrize(
    "fields, trainable",
    [
        ({}, True),
        ({"trust": "explicit"}, True),
        ({"trust": "reviewed"}, True),
        ({"trust": "implicit"}, False),
        ({"ok": "no"}, False),
        ({"split": "test"}, False),
        ({"excluded": True}, False),
    ],
)
def test_trainable_rules(fields, trainable):
    assert is_trainable(clip("c-1", **fields)) is trainable


def test_a_train_clip_that_is_a_frozen_test_clip_is_refused():
    clips = {c.id: c for c in [clip("P1_r001"), clip("P1_t01")]}
    with pytest.raises(OverlapError, match="P1_t01"):
        trainable_clips(clips, {"P1_t01"})


def test_trainable_clips_skip_test_and_implicit_clips():
    clips = {c.id: c for c in [clip("a"), clip("b", split="test"), clip("c", trust="implicit"), clip("d")]}
    assert [c.id for c in trainable_clips(clips, {"b"})] == ["a", "d"]


def test_ten_clips_hold_out_four_for_validation():
    train, val = split_validation([clip(f"r{i:03d}") for i in range(10)], seed=1234)
    assert (len(train), len(val)) == (6, 4)
    assert not {c.id for c in train} & {c.id for c in val}


def test_three_hundred_clips_hold_out_thirty():
    train, val = split_validation([clip(f"r{i:03d}") for i in range(300)], seed=1234)
    assert (len(train), len(val)) == (270, 30)


def test_the_hold_out_is_the_same_every_run():
    clips = [clip(f"r{i:03d}") for i in range(40)]
    assert [c.id for c in split_validation(clips, 7)[1]] == [c.id for c in split_validation(list(reversed(clips)), 7)[1]]


def test_too_few_clips_are_refused_with_a_count():
    with pytest.raises(ValueError, match="there are 7"):
        split_validation([clip(f"r{i}") for i in range(7)], seed=1)


def test_freeze_builds_every_condition_and_remembers_old_test_ids(data_root):
    for record in [clip("P1_t01", split="test"), clip("P1_t01n", split="test", condition="noisy"), clip("P1_t02", split="test", ok="no"), clip("P1_r001")]:
        save_clip(record)
    first = freeze_test_set("P1", load_clips("P1"))
    assert first.conditions == {"quiet": ["P1_t01"], "noisy_real": ["P1_t01n"], "babble_5db": ["P1_t01"], "babble_0db": ["P1_t01"]}

    save_clip(clip("P1_t01", split="test", excluded=True))
    second = freeze_test_set("P1", load_clips("P1"))
    assert second.conditions["quiet"] == []
    assert "P1_t01" in second.all_ids and second.id != first.id


def test_the_last_record_for_an_id_wins(data_root):
    save_clip(clip("c-1", text="First label."))
    save_clip(clip("c-1", text="Corrected label."))
    assert load_clips("P1")["c-1"].text == "Corrected label."
