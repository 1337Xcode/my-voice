"""Correction memory: similarity, recurring pairs and the lookup thresholds."""

import pytest

import voice.storage as storage
from voice.gate.memory import add_pair, load_pairs, lookup, similarity


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)


def test_similarity_is_normalised_edit_distance():
    assert similarity("kitten", "sitting") == pytest.approx(1 - 3 / 7)
    assert similarity("Flat white, please!", "flat white please") == 1.0
    assert similarity("abc", "xyz") == 0.0


def test_recurring_pair_increments_its_count():
    add_pair("P1", "can I have a fat white", ["can I have a fat white"], "Can I have a flat white, please?", "pick")
    second = add_pair("P1", "can I have the fat white", [], "can I have a flat white please", "typed")
    assert second["count"] == 2
    [stored] = load_pairs("P1")
    assert stored["count"] == 2 and stored["meant"] == "Can I have a flat white, please?" and stored["source"] == "pick"


def test_a_different_heard_starts_a_new_pair():
    add_pair("P1", "can I have a fat white", [], "Can I have a flat white, please?", "pick")
    add_pair("P1", "cup of tee", [], "Can I have a cup of tea, please?", "pick")
    assert len(load_pairs("P1")) == 2


def test_lookup_needs_two_confirmations():
    add_pair("P1", "can I have a fat white", [], "Can I have a flat white, please?", "pick")
    assert lookup("P1", "can I have a fat white") == []
    add_pair("P1", "can I have a fat white", [], "Can I have a flat white, please?", "spoken")
    [hit] = lookup("P1", "can I half a fat white")
    assert hit.meant == "Can I have a flat white, please?"
    assert hit.count == 2
    assert hit.similarity == pytest.approx(round(1 - 2 / 22, 3))


def test_lookup_needs_similarity_of_at_least_point_six():
    for _ in range(3):
        add_pair("P1", "where is the station", [], "Where is the station, please?", "pick")
    assert lookup("P1", "can I pay by card") == []
    assert len(lookup("P1", "wear is the stayshun")) == 1


def test_unknown_source_is_refused():
    with pytest.raises(ValueError):
        add_pair("P1", "x", [], "y", "guess")
