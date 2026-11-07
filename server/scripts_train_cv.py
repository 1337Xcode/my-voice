"""Chooses training settings for one speaker by 5-fold cross-validation on his training clips only (never the test set).

Each fold trains the standard trainer (spec 9.3) from the base model on 4/5 of his trainable clips, then decodes the
held-out 1/5 exactly as serving does (`voice.asr.whisper`), clean and mixed with babble at 5 and 0 dB. A variant changes
one trainer setting; its score is the mean over those three conditions of the pooled WER on all held-out clips.

Run: cd server && modal run scripts_train_cv.py --speaker S1 --variants default,rank16 --seeds 1234
Results are appended to speech-data/<speaker>/eval/train_cv.jsonl and printed.
"""

import json
import time
import zlib

import modal

from jobs import TRAIN_GPU, VOLUMES, data_volume, jobs_image

# The job image plus the two app modules this script imports from.
cv_image = jobs_image.add_local_python_source("jobs", "main")
app = modal.App("my-voice-train-cv")

FOLDS = 5
FOLD_SEED = 7
CONDITIONS = {"quiet": None, "babble_5db": 5.0, "babble_0db": 0.0}
# Each variant changes one setting of the default trainer: module attribute -> value.
VARIANTS = {
    "default": {},
    "rank16": {"trainer.LORA_RANK": 16, "trainer.LORA_ALPHA": 32},
    "rank64": {"trainer.LORA_RANK": 64, "trainer.LORA_ALPHA": 128},
    "lr5e-5": {"trainer.LEARNING_RATE": 5e-5},
    "lr2e-4": {"trainer.LEARNING_RATE": 2e-4},
    "patience5": {"trainer.PATIENCE": 5, "trainer.MAX_EPOCHS": 25},
    "no_babble": {"augment.BABBLE_PROBABILITY": 0.0},
    "more_babble": {"augment.BABBLE_PROBABILITY": 0.8, "augment.SNR_RANGE_DB": (-5.0, 15.0)},
    "no_speed": {"augment.SPEEDS": (1.0,)},
    "more_specaug": {"trainer.SPEC_AUGMENT": {"apply_spec_augment": True, "mask_time_prob": 0.1, "mask_time_length": 10, "mask_feature_prob": 0.1, "mask_feature_length": 10}},
    "plus_p1": {"extra_speaker": "P1"},
}


def fold_of(clip_ids: list[str]) -> dict[str, int]:
    """A fixed fold number per clip, from a seeded shuffle of the sorted ids."""
    import random

    ordered = sorted(clip_ids)
    random.Random(FOLD_SEED).shuffle(ordered)
    return {clip_id: index % FOLDS for index, clip_id in enumerate(ordered)}


def apply_overrides(overrides: dict) -> None:
    """Sets the variant's trainer and augmentation constants in this container."""
    from voice.training import augment, trainer

    modules = {"trainer": trainer, "augment": augment}
    for key, value in overrides.items():
        if key == "extra_speaker":
            continue
        module, name = key.split(".")
        setattr(modules[module], name, value)


def held_out_audio(examples, bank) -> dict[str, list]:
    """The held-out clips per condition: clean, and mixed with babble using a fixed per-clip seed (as the test set is)."""
    import numpy as np

    from voice.training.babble import babble_segment, mix_at_snr

    audio = {}
    for condition, snr_db in CONDITIONS.items():
        if snr_db is None:
            audio[condition] = [ex.audio for ex in examples]
            continue
        audio[condition] = []
        for ex in examples:
            rng = np.random.default_rng(zlib.crc32(f"{ex.id}|{condition}".encode()))
            audio[condition].append(mix_at_snr(ex.audio, babble_segment(bank, len(ex.audio), rng), snr_db))
    return audio


def extra_examples(speaker: str):
    """Another speaker's trainable clips (never his test clips), as extra training examples."""
    from voice.clips.records import load_clips
    from voice.clips.selection import load_frozen_test_set, trainable_clips
    from voice.training.improve import load_examples

    frozen = load_frozen_test_set(speaker)
    return load_examples(speaker, trainable_clips(load_clips(speaker), set(frozen.all_ids) if frozen else set()))


@app.function(image=cv_image, volumes=VOLUMES, gpu=TRAIN_GPU, timeout=1800)
def run_fold(speaker: str, variant: str, fold: int, seed: int) -> dict:
    """Trains one fold of one variant and decodes its held-out clips; returns per-clip hypotheses."""
    import gc
    import tempfile
    from pathlib import Path

    import torch

    from voice.asr.whisper import load_whisper
    from voice.clips.records import load_clips
    from voice.clips.selection import load_frozen_test_set, split_validation, trainable_clips
    from voice.training import trainer
    from voice.training.babble import load_babble_bank
    from voice.training.improve import load_examples

    data_volume.reload()
    overrides = VARIANTS[variant]
    apply_overrides(overrides)
    trainer.SEED = seed
    clips = trainable_clips(load_clips(speaker), set(load_frozen_test_set(speaker).all_ids))
    folds = fold_of([clip.id for clip in clips])
    held = [clip for clip in clips if folds[clip.id] == fold]
    rest = [clip for clip in clips if folds[clip.id] != fold]
    # The inner validation split is the one the trainer would make, fixed across seeds.
    train, val = split_validation(rest, seed=1234)
    train_examples, val_examples = load_examples(speaker, train), load_examples(speaker, val)
    if "extra_speaker" in overrides:
        train_examples += extra_examples(overrides["extra_speaker"])
    bank = load_babble_bank()
    with tempfile.TemporaryDirectory() as output:
        result = trainer.train_adapter(train_examples, val_examples, bank, Path(output), "cuda", lambda *_: None)
        gc.collect()
        torch.cuda.empty_cache()
        whisper = load_whisper("cuda")
        whisper.set_adapter(output)
        held_examples = load_examples(speaker, held)
        rows = []
        for condition, audios in held_out_audio(held_examples, bank).items():
            for ex, audio in zip(held_examples, audios):
                rows.append({"id": ex.id, "condition": condition, "reference": ex.text, "hypothesis": whisper.transcribe(audio)})
    return {"variant": variant, "fold": fold, "seed": seed, "train": len(train_examples), "val": len(val_examples), "held": len(held),
            "best_epoch": result.best_epoch, "epochs": result.epochs_run, "train_seconds": result.seconds, "rows": rows}


@app.function(image=cv_image, volumes=VOLUMES, gpu=TRAIN_GPU, timeout=1800)
def run_stock(speaker: str) -> dict:
    """Stock Whisper on every trainable clip, in the same three conditions, for reference."""
    from voice.asr.whisper import load_whisper
    from voice.clips.records import load_clips
    from voice.clips.selection import load_frozen_test_set, trainable_clips
    from voice.training.babble import load_babble_bank
    from voice.training.improve import load_examples

    data_volume.reload()
    examples = load_examples(speaker, trainable_clips(load_clips(speaker), set(load_frozen_test_set(speaker).all_ids)))
    whisper = load_whisper("cuda")
    rows = []
    for condition, audios in held_out_audio(examples, load_babble_bank()).items():
        for ex, audio in zip(examples, audios):
            rows.append({"id": ex.id, "condition": condition, "reference": ex.text, "hypothesis": whisper.transcribe(audio, stock=True)})
    return {"variant": "stock", "fold": -1, "seed": 0, "rows": rows}


def score(rows: list[dict]) -> dict:
    """Pooled WER per condition and their mean."""
    from voice.evaluation.wer import wer_percent

    metrics = {}
    for condition in CONDITIONS:
        chosen = [row for row in rows if row["condition"] == condition]
        metrics[condition] = wer_percent([row["reference"] for row in chosen], [row["hypothesis"] for row in chosen])
    return {**metrics, "mean": round(sum(metrics.values()) / len(metrics), 2), "clips": len(rows) // len(CONDITIONS)}


@app.local_entrypoint()
def main(speaker: str = "S1", variants: str = "default", seeds: str = "1234", stock: bool = False):
    """Runs every fold of every variant and seed in parallel and prints the cross-validated WER."""
    import pathlib

    calls = [(speaker, variant, fold, int(seed)) for variant in variants.split(",") for seed in seeds.split(",") for fold in range(FOLDS)]
    results = list(run_fold.starmap(calls, return_exceptions=True))
    if stock:
        results.append(run_stock.remote(speaker))
    failures = [str(result) for result in results if isinstance(result, Exception)]
    results = [result for result in results if not isinstance(result, Exception)]
    log = pathlib.Path(f"../.work/train_cv_{speaker}.jsonl")
    with log.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps({**result, "logged_at": time.time()}) + "\n")
    groups = {}
    for result in results:
        groups.setdefault((result["variant"], result["seed"]), []).append(result)
    for (variant, seed), parts in sorted(groups.items()):
        epochs = [part.get("best_epoch") for part in parts]
        print(variant, seed, f"folds={len(parts)}", score([row for part in parts for row in part["rows"]]), f"best_epochs={epochs}")
    for failure in failures:
        print("FAILED:", failure[:300])
