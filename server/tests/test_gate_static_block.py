"""The static prefix and the articulation note measured from corrections."""

import pytest

import voice.storage as storage
from voice.gate.memory import add_pair
from voice.gate.static_block import (DEFAULT_NOTE, articulation_note, articulation_stats, build_static_block,
                                     note_from_stats)

TIP = "tongue-tip consonants (t, d, n, l, s, z, r)"
BACK = "back-of-tongue consonants (k, g, hard c)"
LIPS = "lip consonants (p, b, m, f, v, w)"


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)


def test_stats_count_wrong_letters_of_the_meant_sentence_per_sound_class():
    stats = articulation_stats([("fat", "flat"), ("big dog", "big dog")])
    assert stats == {TIP: (1, 3), BACK: (0, 2), LIPS: (0, 2), "vowels": (0, 3)}


def test_stats_count_replaced_letters():
    assert articulation_stats([("tea", "key")])[BACK] == (1, 1)


def test_note_names_the_worst_classes_and_the_most_reliable():
    note = note_from_stats({TIP: (6, 10), BACK: (2, 10), LIPS: (1, 10), "vowels": (0, 10)})
    assert note == (f"Measured from his corrections, the recogniser most often gets these sounds wrong: "
                    f"{TIP} (60% of them), then {BACK} (20% of them); vowels are the most reliable (0% wrong).")


def test_note_without_errors_keeps_the_default():
    assert note_from_stats({TIP: (0, 4), "vowels": (0, 4)}) == DEFAULT_NOTE


def test_note_changes_only_after_thirty_corrections():
    for i in range(29):
        add_pair("P1", f"the og ran {i}", [], f"the dog ran {i}", "pick")
    assert articulation_note("P1") == DEFAULT_NOTE
    add_pair("P1", "the og ran 29", [], "the dog ran 29", "typed")
    assert articulation_note("P1").startswith(f"Measured from his corrections, the recogniser most often gets these sounds wrong: {TIP}")


def test_spoken_and_unchanged_pairs_are_not_corrections():
    for i in range(30):
        add_pair("P1", f"the dog ran {i}", [], f"the dog ran {i}", "pick")
        add_pair("P1", f"a og sat {i}", [], f"a dog sat {i}", "spoken")
    assert articulation_note("P1") == DEFAULT_NOTE


def test_static_block_holds_note_bank_and_vocabulary():
    storage.write_json(storage.speaker_dir("P1") / "vocab.json", {"places": ["Riverside"], "words": ["oat milk"]})
    block = build_static_block("P1")
    assert DEFAULT_NOTE in block
    assert "- Can I have a flat white, please?" in block
    assert "Names, places and words he uses: Riverside, oat milk" in block
    assert block == build_static_block("P1")
