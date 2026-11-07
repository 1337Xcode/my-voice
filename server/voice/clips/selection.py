"""Which clips train and which test: selection rules, the frozen test set and the overlap check."""

import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

from voice.clips.records import TRAINABLE_TRUST, ClipRecord, audio_path
from voice.storage import read_json, speaker_dir, write_json

CONDITIONS = ("quiet", "noisy_real", "babble_5db", "babble_0db")
BABBLE_SNR_DB = {"babble_5db": 5.0, "babble_0db": 0.0}
VALIDATION_FRACTION = 0.1
MIN_VALIDATION = 4
# Below this, a validation set of 4 would leave too few clips to learn from.
MIN_TRAINABLE = 8


class OverlapError(AssertionError):
    """A clip is both a training clip and a frozen test clip."""


def is_trainable(clip: ClipRecord) -> bool:
    """Ok, split train, not excluded, trust read, explicit or reviewed."""
    return clip.ok and clip.split == "train" and not clip.excluded and clip.trust in TRAINABLE_TRUST


def is_testable(clip: ClipRecord) -> bool:
    """A clip that belongs in the test set: ok, split test, not excluded."""
    return clip.ok and clip.split == "test" and not clip.excluded


def assert_no_overlap(train_ids: list[str], test_ids: set[str]) -> None:
    """Raises OverlapError naming every clip that is in both sets."""
    shared = sorted(set(train_ids) & test_ids)
    if shared:
        raise OverlapError(f"{len(shared)} training clips are frozen test clips: {', '.join(shared)}.")


def trainable_clips(clips: dict[str, ClipRecord], frozen_test_ids: set[str]) -> list[ClipRecord]:
    """All trainable clips, sorted by id, after checking none of them is a test clip."""
    chosen = sorted((clip for clip in clips.values() if is_trainable(clip)), key=lambda clip: clip.id)
    assert_no_overlap([clip.id for clip in chosen], frozen_test_ids)
    return chosen


def split_validation(clips: list[ClipRecord], seed: int) -> tuple[list[ClipRecord], list[ClipRecord]]:
    """Holds out 10% (at least 4) for validation with a fixed seed; returns (train, validation)."""
    if len(clips) < MIN_TRAINABLE:
        raise ValueError(f"Training needs at least {MIN_TRAINABLE} trainable clips; there are {len(clips)}.")
    shuffled = sorted(clips, key=lambda clip: clip.id)
    random.Random(seed).shuffle(shuffled)
    count = max(MIN_VALIDATION, round(len(shuffled) * VALIDATION_FRACTION))
    return shuffled[count:], shuffled[:count]


@dataclass
class FrozenTestSet:
    """The frozen test set: clip ids per condition, and every id ever frozen (never trainable)."""

    id: str
    frozen_at: float
    conditions: dict[str, list[str]]
    texts: dict[str, str]
    all_ids: list[str]

    def as_dict(self) -> dict:
        """The JSON form stored on the volume."""
        return self.__dict__.copy()


def frozen_test_set_path(speaker: str) -> Path:
    """Where the frozen test set is stored."""
    return speaker_dir(speaker) / "eval" / "test_set.json"


def condition_audio(speaker: str, condition: str, clip_id: str) -> Path:
    """The audio a test clip is evaluated on in one condition."""
    if condition in BABBLE_SNR_DB:
        return speaker_dir(speaker) / "eval" / condition / f"{clip_id}.wav"
    return audio_path(speaker, clip_id)


def load_frozen_test_set(speaker: str) -> FrozenTestSet | None:
    """The frozen test set, or None before the first freeze."""
    stored = read_json(frozen_test_set_path(speaker), None)
    return FrozenTestSet(**stored) if stored else None


def freeze_test_set(speaker: str, clips: dict[str, ClipRecord]) -> FrozenTestSet:
    """Re-freezes the test set: every testable clip now, and every id frozen before stays untrainable."""
    previous = load_frozen_test_set(speaker)
    testable = sorted((clip for clip in clips.values() if is_testable(clip)), key=lambda clip: clip.id)
    quiet = [clip.id for clip in testable if clip.condition == "quiet"]
    conditions = {
        "quiet": quiet,
        "noisy_real": [clip.id for clip in testable if clip.condition == "noisy"],
        "babble_5db": list(quiet),
        "babble_0db": list(quiet),
    }
    texts = {clip.id: clip.text for clip in testable}
    all_ids = sorted(set(previous.all_ids if previous else []) | set(texts))
    digest = hashlib.sha1(json.dumps([conditions, texts], sort_keys=True).encode()).hexdigest()[:10]
    frozen = FrozenTestSet(id=digest, frozen_at=round(time.time(), 3), conditions=conditions, texts=texts, all_ids=all_ids)
    write_json(frozen_test_set_path(speaker), frozen.as_dict())
    return frozen
