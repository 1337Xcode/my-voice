"""WER per model version per test condition (spec 15.1, 15.2), decoded exactly as serving decodes."""

import time
from pathlib import Path

from voice.audio.pcm import read_audio
from voice.clips.selection import CONDITIONS, FrozenTestSet, condition_audio, load_frozen_test_set
from voice.config import MODELS_ROOT
from voice.evaluation.wer import clip_wer_percent, wer_percent, words_understood
from voice.storage import read_json, speaker_dir, write_json
from voice.training.registry import load_registry, save_registry


def summarise(per_clip: list[dict], test_set_id: str) -> dict:
    """Corpus WER per condition and their mean, from per-clip {condition, reference, hypothesis} rows."""
    metrics = {}
    for condition in CONDITIONS:
        rows = [row for row in per_clip if row["condition"] == condition]
        if rows:
            wer = wer_percent([row["reference"] for row in rows], [row["hypothesis"] for row in rows])
            metrics[condition] = {"wer": wer, "words_understood": words_understood(wer), "n": len(rows)}
    if not metrics:
        raise ValueError("The test set has no clips to score.")
    mean_wer = round(sum(entry["wer"] for entry in metrics.values()) / len(metrics), 2)
    return {"metrics": metrics, "mean_wer": mean_wer, "test_set": test_set_id, "evaluated_at": round(time.time(), 3)}


def score_model(whisper, speaker: str, frozen: FrozenTestSet, adapter: str | None) -> tuple[dict, list[dict]]:
    """Decodes every test clip in every condition with one model (None = stock); returns (scores, per-clip rows)."""
    if adapter is not None:
        whisper.set_adapter(adapter)
    per_clip = []
    for condition in CONDITIONS:
        for clip_id in frozen.conditions.get(condition, []):
            hypothesis = whisper.transcribe(read_audio(condition_audio(speaker, condition, clip_id)), stock=adapter is None)
            reference = frozen.texts[clip_id]
            per_clip.append({"id": clip_id, "condition": condition, "reference": reference, "hypothesis": hypothesis, "wer": clip_wer_percent(reference, hypothesis)})
    return summarise(per_clip, frozen.id), per_clip


def version_folder(entry: dict) -> Path:
    """A registered version's folder on the speech-models volume."""
    return MODELS_ROOT / entry["path"]


def record_version_scores(entry: dict, scores: dict, per_clip: list[dict]) -> None:
    """Stores a version's scores in its registry entry and its per-clip results in its meta.json."""
    entry.update(scores)
    meta_path = version_folder(entry) / "meta.json"
    meta = read_json(meta_path, {})
    meta.update({**scores, "per_clip": per_clip})
    write_json(meta_path, meta)


def eval_asr(whisper, speaker: str) -> dict:
    """Re-scores stock Whisper and every registered version on the frozen test set; updates the registry."""
    frozen = load_frozen_test_set(speaker)
    if frozen is None:
        raise FileNotFoundError(f"{speaker} has no frozen test set yet; import or record test sentences first.")
    registry = load_registry(speaker)
    results = {}
    stock_scores, stock_clips = score_model(whisper, speaker, frozen, None)
    registry["stock"] = stock_scores
    results["stock"] = {**stock_scores, "per_clip": stock_clips}
    for name, entry in sorted(registry["versions"].items(), key=lambda item: item[1]["version"]):
        scores, per_clip = score_model(whisper, speaker, frozen, str(version_folder(entry)))
        record_version_scores(entry, scores, per_clip)
        results[name] = {**scores, "per_clip": per_clip}
    save_registry(registry)
    write_json(speaker_dir(speaker) / "eval" / "asr_results.json", {"test_set": frozen.id, "systems": results})
    return {name: {"mean_wer": result["mean_wer"], "metrics": result["metrics"]} for name, result in results.items()}
