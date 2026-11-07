"""Improve now (spec 9.3) and register_adapter (12.3): make or adopt a version, score it, promote it only if better."""

import json
import logging
import shutil
import time
from typing import Callable

from voice.audio.pcm import read_audio
from voice.clips.records import ClipRecord, audio_path, load_clips
from voice.clips.selection import FrozenTestSet, freeze_test_set, load_frozen_test_set, split_validation, trainable_clips
from voice.config import MODELS_ROOT
from voice.storage import models_dir, write_json
from voice.training.babble import load_babble_bank, make_babble_tests
from voice.training.promotion import evaluate_and_decide
from voice.training.registry import load_registry, model_name, next_version, save_registry, write_status
from voice.training.trainer import HYPERPARAMETERS, Example, train_adapter

log = logging.getLogger("voice.training")
# Seconds between progress writes during training (each write commits the volume).
STATUS_EVERY_S = 10.0


def refreeze_test_set(speaker: str) -> FrozenTestSet:
    """Re-freezes the test set from the current clips and writes its babble versions (onboarding, import)."""
    frozen = freeze_test_set(speaker, load_clips(speaker))
    make_babble_tests(speaker, frozen)
    return frozen


def current_test_set(speaker: str) -> FrozenTestSet:
    """The frozen test set, freezing it now if this is the first run."""
    return load_frozen_test_set(speaker) or refreeze_test_set(speaker)


def training_data(speaker: str, frozen: FrozenTestSet) -> tuple[list[Example], list[Example]]:
    """Trainable clips (never a test clip), split into train and validation examples, counts logged."""
    clips = trainable_clips(load_clips(speaker), set(frozen.all_ids))
    train, val = split_validation(clips, seed=HYPERPARAMETERS["seed"])
    log.info("%s: %d trainable clips (%d train, %d validation), %d frozen test ids, overlap 0", speaker, len(clips), len(train), len(val), len(frozen.all_ids))
    return load_examples(speaker, train), load_examples(speaker, val)


def load_examples(speaker: str, clips: list[ClipRecord]) -> list[Example]:
    """Each clip's stored audio and label."""
    return [Example(clip.id, read_audio(audio_path(speaker, clip.id)), clip.text) for clip in clips]


def throttled_progress(speaker: str, name: str, commit: Callable[[], None]):
    """A progress callback that writes the training status at most every STATUS_EVERY_S seconds."""
    last = [0.0]

    def report(fraction: float, eta_s: float, stage: str) -> None:
        if time.time() - last[0] < STATUS_EVERY_S and fraction < 1.0:
            return
        last[0] = time.time()
        write_status(speaker, "training", f"Training {name}: {stage}", version=name, progress=round(fraction, 3), eta_s=round(eta_s))
        commit()

    return report


def new_entry(registry: dict, speaker: str, source: str, **details) -> str:
    """Adds the next version to the registry (not yet scored) and returns its name."""
    version = next_version(registry)
    name = model_name(speaker, version)
    registry["versions"][name] = {"version": version, "path": f"{speaker}/{name}", "source": source, "created_at": round(time.time(), 3), "status": "evaluating", **details}
    return name


def train_new_version(speaker: str, commit: Callable[[], None]) -> str:
    """Trains a new version from the base model on all trainable clips and registers it unscored; returns its name."""
    write_status(speaker, "queued", "Getting your clips ready")
    commit()
    frozen = current_test_set(speaker)
    train, val = training_data(speaker, frozen)
    registry = load_registry(speaker)
    name = new_entry(registry, speaker, "train", train_clips=len(train) + len(val))
    output = models_dir(speaker) / name
    result = train_adapter(train, val, load_babble_bank(), output, "cuda", throttled_progress(speaker, name, commit))
    meta = {
        "name": name, "base_model": HYPERPARAMETERS["base_model"], "created_at": registry["versions"][name]["created_at"],
        "train_clip_count": len(train), "train_ids": [ex.id for ex in train], "validation_ids": [ex.id for ex in val],
        "hyperparameters": HYPERPARAMETERS, "history": result.history, "best_epoch": result.best_epoch,
        "best_val_wer": result.best_val_wer, "stopped": result.stopped, "train_seconds": result.seconds,
    }
    write_json(output / "meta.json", meta)
    registry["versions"][name].update(train_seconds=result.seconds, epochs=result.epochs_run, best_epoch=result.best_epoch)
    save_registry(registry)
    write_status(speaker, "evaluating", f"Testing {name} on your test sentences", version=name, progress=1.0)
    commit()
    return name


def decide_version(speaker: str, name: str, load_whisper: Callable[[], object], commit: Callable[[], None]) -> dict:
    """Scores a registered version on the frozen test set and promotes it if it beats the active model."""
    return evaluate_and_decide(load_whisper(), load_registry(speaker), name, speaker, current_test_set(speaker), commit)


def register_adapter(speaker: str, source_name: str, load_whisper: Callable[[], object], commit: Callable[[], None]) -> dict:
    """Copies a teammate's adapter from the volume root into the registry as a new version, scores it, promotes if better."""
    source = MODELS_ROOT / source_name
    config_path = source / "adapter_config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"No PEFT adapter at speech-models/{source_name}.")
    base = json.loads(config_path.read_text(encoding="utf-8")).get("base_model_name_or_path")
    if base != HYPERPARAMETERS["base_model"]:
        raise ValueError(f"speech-models/{source_name} adapts {base}, not {HYPERPARAMETERS['base_model']}.")
    frozen = current_test_set(speaker)
    registry = load_registry(speaker)
    name = new_entry(registry, speaker, "register", origin=source_name)
    output = models_dir(speaker) / name
    shutil.copytree(source, output, dirs_exist_ok=True)
    team_config = source / "train_config.json"
    write_json(output / "meta.json", {"name": name, "base_model": base, "origin": source_name, "created_at": registry["versions"][name]["created_at"],
                                      "team_train_config": json.loads(team_config.read_text(encoding="utf-8")) if team_config.is_file() else None})
    save_registry(registry)
    commit()
    return evaluate_and_decide(load_whisper(), registry, name, speaker, frozen, commit)
