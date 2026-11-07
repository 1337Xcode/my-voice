"""His phrase bank (spec 7.4): read, seed from the default list, and replace."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from voice.config import ASSETS_ROOT
from voice.storage import read_json, speaker_dir, write_json

CATEGORIES = ("Social", "Café and shop", "Phone", "Getting around", "Home", "Mine")
MAX_TEMPLATES = 5


class Phrase(BaseModel):
    """One phrase in the bank."""

    id: str
    text: str = Field(min_length=1, max_length=200)
    category: str = "Mine"
    order: int = 0
    pinned: bool = False
    template_clip_ids: list[str] = Field(default_factory=list, max_length=MAX_TEMPLATES)
    tts: dict[str, str] = Field(default_factory=dict)
    uses: int = 0


def bank_path(speaker: str) -> Path:
    return speaker_dir(speaker) / "phrases.json"


def default_bank() -> list[Phrase]:
    """The spec's default phrases (section 11.8), with stable ids p01, p02, ..."""
    by_category = json.loads((ASSETS_ROOT / "default_phrases.json").read_text(encoding="utf-8"))
    phrases: list[Phrase] = []
    for category, texts in by_category.items():
        for text in texts:
            index = len(phrases) + 1
            phrases.append(Phrase(id=f"p{index:02d}", text=text, category=category, order=index))
    return phrases


def load_bank(speaker: str) -> list[Phrase]:
    """His bank, seeded with the defaults the first time it is read."""
    stored = read_json(bank_path(speaker), None)
    if stored is None:
        bank = default_bank()
        save_bank(speaker, bank)
        return bank
    return sorted((Phrase(**entry) for entry in stored), key=lambda phrase: phrase.order)


def save_bank(speaker: str, bank: list[Phrase]) -> None:
    """Writes the whole bank, ordered."""
    ordered = sorted(bank, key=lambda phrase: phrase.order)
    write_json(bank_path(speaker), [phrase.model_dump() for phrase in ordered])
