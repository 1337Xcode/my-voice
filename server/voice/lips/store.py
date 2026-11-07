"""His `lips.json` (EXP-SPEC 9.1): the sync offset per device, enrolment thresholds and the visual confusion map."""

import hashlib
import json

from voice.storage import speaker_dir


def device_key(device: str) -> str:
    """A short stable name for a phone or browser (a hash of what it reports), never the raw string."""
    return hashlib.sha1(device.encode("utf-8")).hexdigest()[:12]


def load_lips(speaker: str) -> dict:
    path = speaker_dir(speaker) / "lips.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"devices": {}}


def save_lips(speaker: str, data: dict) -> None:
    path = speaker_dir(speaker) / "lips.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)
