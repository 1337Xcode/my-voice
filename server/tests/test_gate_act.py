"""The act step's thresholds (spec 8.8): never speak below speak_threshold."""

from voice.gate.act import Action, GateSettings, choose_action, is_confident

DEFAULTS = GateSettings()


def test_confident_top_candidate_is_spoken():
    assert choose_action({"c1": 0.9, "none": 0.1}, DEFAULTS) == Action("speak", ["c1"])
    assert is_confident({"c1": 0.9}, DEFAULTS)


def test_exactly_at_the_threshold_speaks():
    assert choose_action({"c1": 0.85, "c2": 0.15}, DEFAULTS) == Action("speak", ["c1"])


def test_split_evidence_offers_a_pick_in_probability_order():
    assert choose_action({"c1": 0.4, "c2": 0.2, "none": 0.4}, DEFAULTS) == Action("pick", ["c1", "c2"])
    assert not is_confident({"c1": 0.4, "c2": 0.2, "none": 0.4}, DEFAULTS)


def test_pick_shows_at_most_three():
    probabilities = {"c1": 0.1, "c2": 0.3, "c3": 0.2, "c4": 0.15, "none": 0.25}
    assert choose_action(probabilities, DEFAULTS) == Action("pick", ["c2", "c3", "c4"])


def test_mostly_none_asks_again_with_the_top_candidate():
    assert choose_action({"c1": 0.2, "none": 0.8}, DEFAULTS) == Action("again", ["c1"])


def test_just_below_pick_threshold_asks_again():
    assert choose_action({"c1": 0.3, "c2": 0.2, "c3": 0.04, "c4": 0.3, "none": 0.16}, DEFAULTS).kind == "pick"
    assert choose_action({"c1": 0.3, "c2": 0.2, "c3": 0.04, "none": 0.46}, DEFAULTS) == Action("again", ["c1"])


def test_check_first_turns_a_confident_speak_into_a_pick_with_top_first():
    settings = GateSettings(check_first=True)
    assert choose_action({"c1": 0.05, "c2": 0.92, "none": 0.03}, settings) == Action("pick", ["c2", "c1"])


def test_no_candidates_asks_again():
    assert choose_action({"none": 1.0}, DEFAULTS) == Action("again", [])
