"""Clip records (spec 7.3): the team CSV's eight columns plus ours, stored append-only per speaker."""

import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator

from voice.storage import append_jsonl, latest_by_id, speaker_dir

TRAINABLE_TRUST = ("read", "explicit", "reviewed")


class ClipRecord(BaseModel):
    """One recorded clip and its label."""

    id: str
    speaker: str
    text: str
    file: str = ""
    split: Literal["train", "test"] = "train"
    condition: Literal["quiet", "noisy"] = "quiet"
    ok: bool = True
    notes: str = ""
    source: Literal["teach", "import", "use", "review"] = "teach"
    trust: Literal["read", "explicit", "reviewed", "implicit"] = "read"
    phrase_id: str | None = None
    turn_id: str | None = None
    duration_s: float | None = None
    created_at: float | None = None
    excluded: bool = False

    @field_validator("ok", mode="before")
    @classmethod
    def team_yes_no(cls, value):
        """Accepts the team CSV's yes/no as well as true/false."""
        if isinstance(value, str):
            return value.strip().lower() in ("yes", "y", "true", "1")
        return bool(value)


def clips_path(speaker: str) -> Path:
    """The speaker's append-only clip log."""
    return speaker_dir(speaker) / "clips.jsonl"


def audio_path(speaker: str, clip_id: str) -> Path:
    """Where a clip's converted 16 kHz wav lives."""
    return speaker_dir(speaker) / "audio" / f"{clip_id}.wav"


def load_clips(speaker: str) -> dict[str, ClipRecord]:
    """Every clip's latest record, keyed by id."""
    return {clip_id: ClipRecord(**record) for clip_id, record in latest_by_id(clips_path(speaker)).items()}


def save_clip(record: ClipRecord) -> None:
    """Appends a record; the last record for an id wins."""
    if record.created_at is None:
        record.created_at = round(time.time(), 3)
    append_jsonl(clips_path(record.speaker), record.model_dump())
