"""The LoRA trainer (spec 9.3): Whisper large-v3-turbo plus a fresh rank-32 adapter, trained on his clips with early stopping."""

import gc
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from voice.asr.whisper import BASE_MODEL
from voice.evaluation.wer import wer_percent
from voice.training.augment import augment

SEED = 1234
LORA_RANK = 32
LORA_ALPHA = 64
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "out_proj"]
LEARNING_RATE = 1e-4
WARMUP_STEPS = 10
EFFECTIVE_BATCH = 16
MICRO_BATCH = 8
MAX_EPOCHS = 15
PATIENCE = 3
# With few clips an epoch still holds this many augmented examples (4 optimiser steps), so 10 clips can learn.
MIN_EXAMPLES_PER_EPOCH = 64
# Stops before an epoch that would push training past this, keeping the whole job under 6 minutes.
TRAIN_BUDGET_S = 240
# Light SpecAugment, applied by the model itself in training mode.
SPEC_AUGMENT = {"apply_spec_augment": True, "mask_time_prob": 0.05, "mask_time_length": 10, "mask_feature_prob": 0.05, "mask_feature_length": 10}
HYPERPARAMETERS = {
    "base_model": BASE_MODEL, "rank": LORA_RANK, "alpha": LORA_ALPHA, "dropout": LORA_DROPOUT, "targets": LORA_TARGETS,
    "lr": LEARNING_RATE, "schedule": "cosine", "warmup_steps": WARMUP_STEPS, "effective_batch": EFFECTIVE_BATCH,
    "micro_batch": MICRO_BATCH, "precision": "bf16", "seed": SEED, "max_epochs": MAX_EPOCHS, "patience": PATIENCE,
    "min_examples_per_epoch": MIN_EXAMPLES_PER_EPOCH, "spec_augment": SPEC_AUGMENT,
}


@dataclass
class Example:
    """One clip ready for training: its audio and label."""

    id: str
    audio: np.ndarray
    text: str


@dataclass
class TrainResult:
    """What a training run produced."""

    epochs_run: int
    best_epoch: int
    best_val_wer: float
    history: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    stopped: str = ""


Progress = Callable[[float, float, str], None]


def load_model(device: str):
    """The base model in bf16 with a fresh LoRA adapter on q/k/v/out projections of encoder and decoder."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    processor = WhisperProcessor.from_pretrained(BASE_MODEL, language="english", task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL, dtype=torch.bfloat16, attn_implementation="sdpa")
    model.config.update(SPEC_AUGMENT)
    model.generation_config.forced_decoder_ids = None
    config = LoraConfig(r=LORA_RANK, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT, target_modules=LORA_TARGETS, bias="none")
    return get_peft_model(model, config).to(device), processor


def encode_batch(processor, audios: list[np.ndarray], texts: list[str], device: str):
    """Log-mel features and label ids (prefix tokens kept, start token dropped, padding masked as -100)."""
    import torch

    features = processor.feature_extractor(audios, sampling_rate=16_000, return_tensors="pt", device=device).input_features
    # Whisper decodes words with a leading space; labels match what it produces.
    ids = processor.tokenizer([" " + text.strip() for text in texts]).input_ids
    start = processor.tokenizer.convert_tokens_to_ids("<|startoftranscript|>")
    ids = [row[1:] if row and row[0] == start else row for row in ids]
    labels = torch.full((len(ids), max(map(len, ids))), -100, dtype=torch.long)
    for index, row in enumerate(ids):
        labels[index, : len(row)] = torch.tensor(row)
    return features.to(device, dtype=torch.bfloat16), labels.to(device)


def epoch_order(count: int, rng: np.random.Generator) -> list[int]:
    """Example indices for one epoch: shuffled passes until MIN_EXAMPLES_PER_EPOCH, cut to whole batches when possible."""
    order: list[int] = []
    while len(order) < max(count, MIN_EXAMPLES_PER_EPOCH):
        order.extend(rng.permutation(count).tolist())
    return order[: max(count, MIN_EXAMPLES_PER_EPOCH)]


def train_epoch(model, processor, optimizer, scheduler, train: list[Example], bank, rng, device: str, on_step: Callable[[], None]) -> float:
    """One epoch of augmented examples in micro-batches, stepping every EFFECTIVE_BATCH examples; returns mean loss."""
    import torch

    model.train()
    order, losses = epoch_order(len(train), rng), []
    for start in range(0, len(order), EFFECTIVE_BATCH):
        step = order[start : start + EFFECTIVE_BATCH]
        for micro in range(0, len(step), MICRO_BATCH):
            chosen = [train[index] for index in step[micro : micro + MICRO_BATCH]]
            features, labels = encode_batch(processor, [augment(ex.audio, bank, rng) for ex in chosen], [ex.text for ex in chosen], device)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(input_features=features, labels=labels).loss
            (loss * len(chosen) / len(step)).backward()
            losses.append(float(loss.detach()))
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad(set_to_none=True)
        on_step()
    return float(np.mean(losses))


def validate(model, processor, val: list[Example], device: str) -> tuple[float, float]:
    """(WER %, mean loss) on the clean validation clips, greedy decoding for speed."""
    import torch

    model.eval()
    hypotheses, losses = [], []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for start in range(0, len(val), MICRO_BATCH):
            chosen = val[start : start + MICRO_BATCH]
            features, labels = encode_batch(processor, [ex.audio for ex in chosen], [ex.text for ex in chosen], device)
            losses.append(float(model(input_features=features, labels=labels).loss))
            ids = model.generate(input_features=features, num_beams=1, do_sample=False, language="en", task="transcribe", max_new_tokens=128)
            hypotheses += processor.batch_decode(ids, skip_special_tokens=True)
    return wer_percent([ex.text for ex in val], hypotheses), float(np.mean(losses))


def adapter_state(model) -> dict:
    """A CPU copy of the LoRA weights, to restore the best epoch later."""
    return {name: tensor.detach().to("cpu", copy=True) for name, tensor in model.state_dict().items() if "lora_" in name}


def train_adapter(train: list[Example], val: list[Example], bank: list[np.ndarray], output: Path, device: str, progress: Progress) -> TrainResult:
    """Trains from the base model, keeps the best epoch by validation WER (then loss), and saves adapter and processor."""
    import torch
    from transformers import get_cosine_schedule_with_warmup

    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    model, processor = load_model(device)
    steps_per_epoch = math.ceil(max(len(train), MIN_EXAMPLES_PER_EPOCH) / EFFECTIVE_BATCH)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LEARNING_RATE)
    scheduler = get_cosine_schedule_with_warmup(optimizer, WARMUP_STEPS, steps_per_epoch * MAX_EPOCHS)
    result = run_epochs(model, processor, optimizer, scheduler, train, val, bank, rng, device, steps_per_epoch, progress)
    model.save_pretrained(str(output))
    processor.save_pretrained(str(output))
    # Free the training copy so evaluation can load the serving model on the same GPU.
    del model, optimizer, scheduler
    gc.collect()
    torch.cuda.empty_cache()
    return result


def run_epochs(model, processor, optimizer, scheduler, train, val, bank, rng, device, steps_per_epoch, progress) -> TrainResult:
    """The epoch loop: train, validate, keep the best weights, stop on patience, the epoch cap or the time budget."""
    started, steps_done = time.time(), [0]
    total_steps = steps_per_epoch * MAX_EPOCHS
    best, best_key, result = None, (math.inf, math.inf), TrainResult(0, 0, math.inf)

    def on_step():
        steps_done[0] += 1
        elapsed = time.time() - started
        progress(steps_done[0] / total_steps, elapsed / steps_done[0] * (total_steps - steps_done[0]), f"epoch {result.epochs_run + 1}")

    for epoch in range(1, MAX_EPOCHS + 1):
        train_loss = train_epoch(model, processor, optimizer, scheduler, train, bank, rng, device, on_step)
        val_wer, val_loss = validate(model, processor, val, device)
        result.epochs_run, elapsed = epoch, time.time() - started
        result.history.append({"epoch": epoch, "train_loss": round(train_loss, 4), "val_loss": round(val_loss, 4), "val_wer": val_wer, "seconds": round(elapsed, 1)})
        if (val_wer, val_loss) < best_key:
            best, best_key, result.best_epoch, result.best_val_wer = adapter_state(model), (val_wer, val_loss), epoch, val_wer
        if epoch - result.best_epoch >= PATIENCE:
            result.stopped = f"no validation gain for {PATIENCE} epochs"
            break
        if elapsed + elapsed / epoch > TRAIN_BUDGET_S:
            result.stopped = f"time budget of {TRAIN_BUDGET_S} s"
            break
    model.load_state_dict(best, strict=False)
    result.seconds = round(time.time() - started, 1)
    result.stopped = result.stopped or f"{MAX_EPOCHS} epochs"
    return result
