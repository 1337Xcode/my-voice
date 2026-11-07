"""The model registry: every version with metrics, the active version, the stock baseline, and the promotion rule (9.3).

registry.json: {"speaker", "active": name or null, "stock": {"metrics", "mean_wer", "test_set"},
"versions": {name: {"version", "path", "source", "created_at", "train_clips", "metrics", "mean_wer", "test_set", "status"}}}.
`metrics` maps each test condition to {"wer", "words_understood", "n"}; `path` is relative to the speech-models volume.
"""

import time
from pathlib import Path

from voice.storage import models_dir, read_json, write_json

# Mean WER must drop by at least this many points, and quiet WER may rise by at most this many.
MIN_MEAN_GAIN = 0.5
MAX_QUIET_LOSS = 1.0


def registry_path(speaker: str) -> Path:
    """The speaker's registry file on the speech-models volume."""
    return models_dir(speaker) / "registry.json"


def load_registry(speaker: str) -> dict:
    """The registry, or an empty one before the first evaluation."""
    return read_json(registry_path(speaker), {"speaker": speaker, "active": None, "stock": None, "versions": {}})


def save_registry(registry: dict) -> None:
    """Writes the registry atomically."""
    registry["updated_at"] = round(time.time(), 3)
    write_json(registry_path(registry["speaker"]), registry)


def model_name(speaker: str, version: int) -> str:
    """`<speaker lowercase>-whisper-lora-v<N>`."""
    return f"{speaker.lower()}-whisper-lora-v{version}"


def next_version(registry: dict) -> int:
    """The number the next version gets."""
    return 1 + max((entry["version"] for entry in registry["versions"].values()), default=0)


def active_scores(registry: dict) -> dict | None:
    """The metrics the active model is judged by: the active version's, or stock's while none is active."""
    return registry["versions"][registry["active"]] if registry.get("active") else registry.get("stock")


def should_promote(candidate: dict, active: dict) -> tuple[bool, str]:
    """The promotion rule on two score entries ({"mean_wer", "metrics": {condition: {"wer"}}}): (promote?, why)."""
    gain = active["mean_wer"] - candidate["mean_wer"]
    if gain < MIN_MEAN_GAIN:
        return False, f"mean WER {candidate['mean_wer']:.2f} vs {active['mean_wer']:.2f}, needs {MIN_MEAN_GAIN} points lower"
    quiet_new = candidate["metrics"].get("quiet", {}).get("wer")
    quiet_old = active["metrics"].get("quiet", {}).get("wer")
    if quiet_new is not None and quiet_old is not None and quiet_new - quiet_old > MAX_QUIET_LOSS:
        return False, f"quiet WER {quiet_new:.2f} vs {quiet_old:.2f}, more than {MAX_QUIET_LOSS} point worse"
    return True, f"mean WER {candidate['mean_wer']:.2f} vs {active['mean_wer']:.2f}"


def mark_failed(speaker: str, name: str, error: str) -> None:
    """Records that a version's training or scoring failed, so it is never mistaken for a scored version."""
    registry = load_registry(speaker)
    if name in registry["versions"]:
        registry["versions"][name].update(status="failed", error=error[:300])
        save_registry(registry)


def status_path(speaker: str) -> Path:
    """Training progress the server reads and pushes to the app."""
    return models_dir(speaker) / "train_status.json"


def write_status(speaker: str, state: str, message: str, **details) -> dict:
    """Writes the training status: queued, training, evaluating, promoted, not_better or failed."""
    status = {"speaker": speaker, "state": state, "message": message, "updated_at": round(time.time(), 3), **details}
    write_json(status_path(speaker), status)
    return status
