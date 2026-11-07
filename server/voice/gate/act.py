"""Turns gate probabilities into speak, pick or again, never speaking below the threshold."""

from dataclasses import dataclass

from voice.gate.decide import NONE_ID

PICK_SIZE = 3


@dataclass(frozen=True)
class GateSettings:
    """The thresholds and his "Before speaking" setting that decide what the app does."""

    speak_threshold: float = 0.85
    pick_threshold: float = 0.55
    check_first: bool = False


@dataclass(frozen=True)
class Action:
    """What to do with this turn, and the candidate ids to show, best first."""

    kind: str  # "speak", "pick" or "again"
    ids: list[str]


def ranked(probabilities: dict[str, float]) -> list[tuple[str, float]]:
    """Candidate ids with their probability, most likely first, without 'none'."""
    return sorted(((k, p) for k, p in probabilities.items() if k != NONE_ID), key=lambda item: item[1], reverse=True)


def is_confident(probabilities: dict[str, float], settings: GateSettings) -> bool:
    """Round 1 may act at once: the top candidate reaches the speak threshold."""
    top = ranked(probabilities)
    return bool(top) and top[0][1] >= settings.speak_threshold


def choose_action(probabilities: dict[str, float], settings: GateSettings) -> Action:
    """Speak at or above speak_threshold (pick, top first, when he checks first); pick if the top 3 sum to pick_threshold; else again."""
    top = ranked(probabilities)
    shown = [cid for cid, p in top[:PICK_SIZE] if p > 0]
    if top and top[0][1] >= settings.speak_threshold:
        return Action("pick", shown) if settings.check_first else Action("speak", [top[0][0]])
    if sum(p for _, p in top[:PICK_SIZE]) >= settings.pick_threshold:
        return Action("pick", shown)
    return Action("again", [top[0][0]] if top else [])
