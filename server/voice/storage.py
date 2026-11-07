"""Paths and file helpers for the speech-data and speech-models volumes."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from voice.config import DATA_ROOT, MODELS_ROOT, SPEAKERS


def check_speaker(speaker: str) -> str:
    """Returns the speaker id if it is one we know, so paths can never escape the volume."""
    if speaker not in SPEAKERS:
        raise ValueError(f"Unknown speaker {speaker!r}; expected one of {', '.join(SPEAKERS)}.")
    return speaker


def speaker_dir(speaker: str) -> Path:
    """The speaker's folder on the speech-data volume."""
    return DATA_ROOT / check_speaker(speaker)


def models_dir(speaker: str) -> Path:
    """The speaker's folder on the speech-models volume."""
    return MODELS_ROOT / check_speaker(speaker)


def shared_dir(*parts: str) -> Path:
    """A folder under speech-data/_shared, for the babble bank and prompt lists."""
    return DATA_ROOT.joinpath("_shared", *parts)


def read_json(path: Path, default: Any) -> Any:
    """Reads a JSON file, or returns the default when it does not exist yet."""
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Writes JSON atomically, so a crash never leaves half a file on the volume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as tmp:
        json.dump(value, tmp, ensure_ascii=False, indent=2)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def append_jsonl(path: Path, record: dict) -> None:
    """Appends one record to a JSON-lines file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterator[dict]:
    """Yields every record of a JSON-lines file, skipping a torn final line."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A container killed mid-write can leave a partial last line; the rest is intact.
                continue


def latest_by_id(path: Path, key: str = "id") -> dict[str, dict]:
    """Folds an append-only JSON-lines file into its latest record per id."""
    latest: dict[str, dict] = {}
    for record in read_jsonl(path):
        latest[record[key]] = record
    return latest
