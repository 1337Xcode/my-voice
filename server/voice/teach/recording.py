"""Teach recordings and live-turn audio becoming clips."""

import re
import time
from pathlib import Path

import numpy as np

from voice.audio.pcm import SAMPLE_RATE, read_audio, write_wav
from voice.clips.convert import decode_audio, prepare_clip
from voice.clips.records import ClipRecord, audio_path, load_clips, save_clip
from voice.phrases.bank import MAX_TEMPLATES, load_bank, save_bank
from voice.storage import speaker_dir

TEST_PROMPT_ID = re.compile(r"^ta(0[1-9]|10)$")
PHRASE_TEST_NOTE = "phrase_test"


def new_clip_id() -> str:
    """An app clip id: c-<milliseconds>."""
    return f"c-{int(time.time() * 1000)}"


def store_upload(speaker: str, raw: bytes, suffix: str, text: str, phrase_id: str | None, prompt_id: str | None,
                 split: str, condition: str) -> ClipRecord:
    """Keeps the original upload, converts it to the stored wav and records the clip; returns the record."""
    clip_id = prompt_id if prompt_id and TEST_PROMPT_ID.match(prompt_id) else new_clip_id()
    if TEST_PROMPT_ID.match(clip_id):
        split = "test"
    raw_path = speaker_dir(speaker) / "raw" / f"{clip_id}{suffix}"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    # The app uploads WAV from its capture path; other formats (team m4a) go through ffmpeg.
    audio = prepare_clip(read_audio(raw_path) if suffix.lower() == ".wav" else decode_audio(raw_path))
    if audio.size < SAMPLE_RATE // 4:
        raise ValueError("That recording is too short. Try again, and speak after tapping Record.")
    write_wav(audio_path(speaker, clip_id), audio)
    notes = PHRASE_TEST_NOTE if phrase_id and split == "test" else (f"prompt:{prompt_id}" if prompt_id else "")
    record = ClipRecord(id=clip_id, speaker=speaker, text=text.strip(), file=f"{clip_id}.wav", split=split, condition=condition,
                        source="teach", trust="read", phrase_id=phrase_id, duration_s=round(audio.size / SAMPLE_RATE, 3), notes=notes)
    save_clip(record)
    if phrase_id and split == "train":
        add_phrase_template(speaker, phrase_id, clip_id)
    return record


def add_phrase_template(speaker: str, phrase_id: str, clip_id: str) -> str | None:
    """Adds a clip as one of a phrase's templates (the 5 most recent are kept); returns the phrase text."""
    bank = load_bank(speaker)
    phrase = next((p for p in bank if p.id == phrase_id), None)
    if phrase is None:
        return None
    phrase.template_clip_ids = (phrase.template_clip_ids + [clip_id])[-MAX_TEMPLATES:]
    save_bank(speaker, bank)
    return phrase.text


def keep_turn_audio(speaker: str, turn_id: str, audio: np.ndarray, text: str, trust: str, phrase_id: str | None) -> ClipRecord:
    """Stores a live turn's audio as a clip (only when "Learn from my conversations" is on)."""
    clip_id = f"c-{turn_id}" if not turn_id.startswith("c-") else turn_id
    write_wav(audio_path(speaker, clip_id), prepare_clip(audio))
    record = ClipRecord(id=clip_id, speaker=speaker, text=text, file=f"{clip_id}.wav", split="train", condition="quiet",
                        source="use", trust=trust, phrase_id=phrase_id, turn_id=turn_id, duration_s=round(audio.size / SAMPLE_RATE, 3))
    save_clip(record)
    return record


def review_items(speaker: str) -> list[dict]:
    """Everyday turns waiting for his ✓ or ✗, newest first."""
    clips = [c for c in load_clips(speaker).values() if c.trust == "implicit" and not c.excluded]
    clips.sort(key=lambda c: c.created_at or 0, reverse=True)
    return [{"turn_id": c.turn_id or c.id, "clip_id": c.id, "text": c.text, "created_at": c.created_at, "duration_s": c.duration_s} for c in clips]


def apply_review(speaker: str, turn_id: str, action: str, text: str | None) -> ClipRecord:
    """Approve makes the clip trainable; reject excludes it; edit fixes the text and approves it."""
    clip = next((c for c in load_clips(speaker).values() if c.turn_id == turn_id or c.id == turn_id), None)
    if clip is None:
        raise KeyError(turn_id)
    if action == "reject":
        clip.excluded = True
    else:
        clip.trust, clip.source = "reviewed", "review"
        if action == "edit" and text and text.strip():
            clip.text = text.strip()
    save_clip(clip)
    return clip


def clip_audio_file(speaker: str, clip_id: str) -> Path:
    """The stored wav for a clip, for playback in Review."""
    return audio_path(speaker, clip_id)
