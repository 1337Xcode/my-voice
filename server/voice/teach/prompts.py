"""The next Teach prompt, in order: his phrases twice each, then Harvard lists 2 onward."""

from voice.clips.records import ClipRecord, load_clips
from voice.config import ASSETS_ROOT
from voice.phrases.bank import load_bank
from voice.storage import read_json, shared_dir
from voice.teach.recording import PHRASE_TEST_NOTE

# Recordings per phrase during the first pass: one template, then one held out for the phrase test set.
FIRST_PASS_PER_PHRASE = 2


def harvard() -> dict:
    """The Harvard lists fetched at build time (`build_prompts`), or the bundled copy if the volume has none yet."""
    stored = read_json(shared_dir("prompts") / "harvard.json", None)
    return stored or read_json(ASSETS_ROOT / "harvard.json", {"test": [], "teach": []})


def test_sentences(speaker: str) -> list[dict]:
    """Harvard list 1 as onboarding test prompts ta01..ta10, each with whether it's recorded."""
    clips = load_clips(speaker)
    return [{**item, "recorded": item["id"] in clips and not clips[item["id"]].excluded} for item in harvard()["test"]]


def _phrase_prompt(speaker: str, clips: list[ClipRecord]) -> dict | None:
    """The first phrase that still needs a recording, and whether this one is a template or the held-out repeat."""
    for phrase in load_bank(speaker):
        mine = [c for c in clips if c.phrase_id == phrase.id and not c.excluded]
        if len(mine) >= FIRST_PASS_PER_PHRASE:
            continue
        has_test = any(c.notes == PHRASE_TEST_NOTE for c in mine)
        split = "test" if mine and not has_test else "train"
        return {"kind": "phrase", "text": phrase.text, "phrase_id": phrase.id, "split": split, "condition": "quiet",
                "progress": {"done": len(mine), "of": FIRST_PASS_PER_PHRASE}}
    return None


def next_prompt(speaker: str) -> dict:
    """Phrases first, then the next unrecorded Harvard sentence; then `like_yours` (the route asks Haiku for its text)."""
    clips = list(load_clips(speaker).values())
    phrase = _phrase_prompt(speaker, clips)
    if phrase:
        return phrase
    recorded = {c.notes.removeprefix("prompt:") for c in clips if c.notes.startswith("prompt:")}
    for item in harvard()["teach"]:
        if item["id"] not in recorded:
            return {"kind": "harvard", "text": item["text"], "prompt_id": item["id"], "split": "train", "condition": "quiet"}
    return {"kind": "like_yours", "text": "", "split": "train", "condition": "quiet"}


def progress(speaker: str) -> dict:
    """Clips recorded today and total minutes recorded, for the Record card."""
    import time

    clips = [c for c in load_clips(speaker).values() if not c.excluded]
    start_of_day = time.time() - (time.time() % 86400)
    return {"today": sum((c.created_at or 0) >= start_of_day for c in clips),
            "minutes": round(sum(c.duration_s or 0 for c in clips) / 60, 1), "total": len(clips)}
