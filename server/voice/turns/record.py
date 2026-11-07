"""Turn records: every stage's timestamp, the candidates, the action and the outcome."""

import time
from dataclasses import asdict, dataclass, field

from voice.storage import append_jsonl, latest_by_id, speaker_dir

STAGES = (
    "t_first_audio", "t_end_of_speech", "t_asr", "t_phrase", "t_round1", "t_repair", "t_round2",
    "t_result_sent", "t_tts_first_byte", "t_tts_done",
)


def now_ms() -> int:
    """Server time in milliseconds."""
    return int(time.time() * 1000)


@dataclass
class TurnRecord:
    """One turn, written to `<speaker>/turns.jsonl` at each milestone; the last line per turn_id wins."""

    turn_id: str
    speaker: str
    mode: str
    model_version: str
    audio_kept: bool = False
    t_first_audio: int | None = None
    t_end_of_speech: int | None = None
    t_asr: int | None = None
    t_phrase: int | None = None
    t_round1: int | None = None
    t_repair: int | None = None
    t_round2: int | None = None
    t_result_sent: int | None = None
    t_tts_first_byte: int | None = None
    t_tts_done: int | None = None
    ms_end_to_text: int | None = None
    ms_end_to_audio: int | None = None
    end_reason: str | None = None
    candidates: list[dict] = field(default_factory=list)
    action: str | None = None
    final_text: str | None = None
    outcome: str | None = None
    asr: dict = field(default_factory=dict)
    gate: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # Experiment data (EXP-SPEC: streamed voice, lips); stays empty when the experiments are off.
    exp: dict = field(default_factory=dict)

    def mark(self, stage: str) -> None:
        """Stamps a stage with the current server time."""
        assert stage in STAGES, stage
        setattr(self, stage, now_ms())

    def stage_ms(self) -> dict[str, int]:
        """Each stamped stage as milliseconds after the end of speech, for logs and the app."""
        end = self.t_end_of_speech
        if end is None:
            return {}
        return {stage[2:]: getattr(self, stage) - end for stage in STAGES[2:] if getattr(self, stage) is not None}

    def save(self) -> None:
        """Appends the record's current state."""
        append_jsonl(speaker_dir(self.speaker) / "turns.jsonl", asdict(self))


def load_turns(speaker: str) -> list[dict]:
    """Every turn's latest record, oldest first."""
    return list(latest_by_id(speaker_dir(speaker) / "turns.jsonl", key="turn_id").values())
