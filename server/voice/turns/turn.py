"""One live turn: its audio, its record, and what was decided (spec 8)."""

from dataclasses import dataclass, field

from voice.audio.endpointing import TurnAudio
from voice.turns.record import TurnRecord

MODES = ("talk", "handsfree", "call", "tell", "them")


@dataclass
class Candidate:
    """A sentence the app may show or speak, with where it came from and its probability."""

    id: str
    text: str
    p: float
    sources: list[str] = field(default_factory=list)

    def as_message(self) -> dict:
        return {"id": self.id, "text": self.text, "p": round(self.p, 4), "sources": self.sources}


@dataclass
class Turn:
    """A turn from start_turn to its outcome."""

    record: TurnRecord
    audio: TurnAudio
    state: str = "listening"  # listening -> processing -> decided -> finished
    candidates: list[Candidate] = field(default_factory=list)
    all_candidates: list[Candidate] = field(default_factory=list)
    nbest: list = field(default_factory=list)
    phrase_matches: list = field(default_factory=list)
    action: str | None = None

    @property
    def id(self) -> str:
        return self.record.turn_id

    @property
    def mode(self) -> str:
        return self.record.mode

    def candidate(self, candidate_id: str) -> Candidate | None:
        """The candidate with this id, if the turn offered it."""
        return next((c for c in self.candidates if c.id == candidate_id), None)
