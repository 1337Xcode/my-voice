"""Measures the phrase matcher on real speech on a Modal A10G: distance distributions, reject rates and speed.

Run: cd server && modal run scripts_phrase_eval.py

Data: the first speaker's Harvard-sentence recordings (`P1/wav/*.wav`, labels in `P1/clips.csv`). Every sentence is
said once, so there are no repeats to measure accuracy on yet; the script reports what the data can honestly show
(how far apart different sentences land, and the reject rate with the conservative default threshold) and the
speed of a 50-phrase x 3-template match. When repeated phrase recordings exist in the bank, the same
`leave_one_out` and `choose_layer` calls measure accuracy.
"""

import json

import modal

app = modal.App("my-voice-phrase-eval")
data_volume = modal.Volume.from_name("speech-data")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "transformers", "silero-vad", "soundfile", "numpy", "pydantic")
    .env({"SPEECH_DATA_ROOT": "/data"})
    .add_local_python_source("voice")
)

SPEAKER = "P1"
LAYERS = list(range(3, 10))
SEGMENT_GAP_MS = 250
MIN_SEGMENT_S = 0.4
BENCH_PHRASES, BENCH_TEMPLATES, BENCH_QUERY_S = 50, 3, 2.0
TIMING_RUNS = 40


def _load_clips() -> list[tuple[str, str, "numpy.ndarray"]]:
    """Reads P1's clips.csv and wavs: (clip id, sentence, 16 kHz mono float32 audio)."""
    import csv

    import numpy as np
    import soundfile as sf

    root = f"/data/{SPEAKER}"
    clips = []
    with open(f"{root}/clips.csv", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            audio, rate = sf.read(f"{root}/wav/{row['id']}.wav", dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if rate != 16_000:
                raise ValueError(f"{row['id']} is {rate} Hz, expected 16000.")
            clips.append((row["id"], row["text"], np.ascontiguousarray(audio)))
    return clips


def _distribution(values) -> dict:
    """Summary percentiles of a list of distances, rounded for reading."""
    import numpy as np

    names = {"min": 0, "p1": 1, "p5": 5, "p25": 25, "median": 50, "p75": 75, "p95": 95, "max": 100}
    return {"count": len(values), **{k: round(float(np.percentile(values, q)), 4) for k, q in names.items()}}


def _sentence_pairs(model, extractor, trim) -> dict:
    """Each sentence as its own phrase with one template: cross-sentence distances and reject rate, per layer."""
    import numpy as np

    from voice.phrases.features import utterance_features
    from voice.phrases.matcher import loo_report, pairwise_distances

    clips = _load_clips()
    per_clip = [utterance_features(model, extractor, "cuda", audio, LAYERS, trim) for _, _, audio in clips]
    owner = np.arange(len(clips))
    ids, texts = [c[0] for c in clips], [c[1] for c in clips]
    report = {"n_clips": len(clips), "layers": {}}
    for layer in LAYERS:
        matrix = pairwise_distances([c[layer] for c in per_clip])
        off_diagonal = matrix[np.triu_indices(len(clips), k=1)]
        loo = loo_report(matrix, owner, ids, texts)
        report["layers"][layer] = {
            "cross_sentence_distance": _distribution(off_diagonal),
            "reject_rate_default_threshold": loo["orphan_reject_rate"],
        }
    return report


def _speech_segments(clips, layer, model, extractor) -> dict:
    """Splits each wav at pauses into natural VAD segments; reports distances inside vs across sentences."""
    import numpy as np
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    from voice.phrases.features import utterance_features
    from voice.phrases.matcher import pairwise_distances

    vad = load_silero_vad()
    identity = lambda audio: audio  # noqa: E731  segments are already cut at speech boundaries
    frames, sentence = [], []
    for index, (_, _, audio) in enumerate(clips):
        spans = get_speech_timestamps(
            torch.from_numpy(audio), vad, sampling_rate=16_000, min_silence_duration_ms=SEGMENT_GAP_MS
        )
        for span in spans:
            if (span["end"] - span["start"]) / 16_000 >= MIN_SEGMENT_S:
                piece = audio[span["start"] : span["end"]]
                frames.append(utterance_features(model, extractor, "cuda", piece, [layer], identity)[layer])
                sentence.append(index)
    matrix = pairwise_distances(frames)
    sentence = np.array(sentence)
    upper = np.triu_indices(len(frames), k=1)
    same = sentence[upper[0]] == sentence[upper[1]]
    values = matrix[upper]
    return {
        "layer": layer,
        "n_segments": len(frames),
        "same_sentence_segments": _distribution(values[same]) if same.any() else None,
        "different_sentence_segments": _distribution(values[~same]),
    }


def _pipeline_check(model, extractor) -> dict:
    """End to end with Silero trimming: each clip padded with 0.5 s of silence must find its own saved copy."""
    import numpy as np

    from voice.phrases.matcher import PhraseMatcher

    clips = _load_clips()[:10]
    matcher = PhraseMatcher(model, extractor, "cuda")
    matcher.set_templates({cid: (text, [audio]) for cid, text, audio in clips})
    padded = [np.concatenate([np.zeros(8000, np.float32), audio, np.zeros(8000, np.float32)]) for _, _, audio in clips]
    results = [matcher.match(audio) for audio in padded]
    found = sum(r.matches and r.matches[0].phrase_id == clip[0] for r, clip in zip(results, clips))
    return {
        "own_copy_found": f"{found}/{len(clips)}",
        "best_distance_max": round(max(r.best_distance for r in results), 4),
        "unrelated_query_rejected": matcher.match(_load_clips()[15][2]).rejected,
        "calibration": str(matcher.calibration()),
    }


def _bench_templates(clips, trim, crop_seconds):
    """150 real recordings for the speed benchmark: the P1 clips, trimmed and repeated (a speed test only)."""
    templates = {}
    cropped = [trim(audio)[: int(crop_seconds * 16_000)] if crop_seconds else trim(audio) for _, _, audio in clips]
    for k in range(BENCH_PHRASES):
        templates[f"bench{k:02d}"] = ("benchmark phrase", [cropped[(k * BENCH_TEMPLATES + t) % len(cropped)] for t in range(BENCH_TEMPLATES)])
    return templates


def _timing(model, extractor, trim, crop_seconds) -> dict:
    """Median and p95 of PhraseMatcher.match for 50 phrases x 3 templates and a ~2 s query, GPU and VAD costs split."""
    import time

    import numpy as np

    from voice.phrases.matcher import PhraseMatcher

    clips = _load_clips()
    templates = _bench_templates(clips, trim, crop_seconds)
    matcher = PhraseMatcher(model, extractor, "cuda", trim=lambda audio: audio)
    matcher.set_templates(templates)
    raw_query = clips[3][2]
    start = time.perf_counter()
    trimmed = trim(raw_query)[: int(BENCH_QUERY_S * 16_000)]
    trim_ms = (time.perf_counter() - start) * 1000
    for _ in range(5):
        matcher.match(trimmed)
    runs = [matcher.match(trimmed).ms for _ in range(TIMING_RUNS)]
    return {
        "templates": BENCH_PHRASES * BENCH_TEMPLATES,
        "template_crop_s": crop_seconds or "full length",
        "query_s": round(len(trimmed) / 16_000, 2),
        "match_ms_median": round(float(np.median(runs)), 1),
        "match_ms_p95": round(float(np.percentile(runs, 95)), 1),
        "silero_trim_ms_one_call_cpu": round(trim_ms, 1),
    }


@app.function(image=image, gpu="A10G", volumes={"/data": data_volume}, timeout=1800)
def run_evaluation() -> dict:
    """Runs every measurement on the GPU and returns them as one JSON-friendly dict."""
    import torch

    from voice.phrases.features import make_silero_trim
    from voice.phrases.matcher import load_wavlm

    model, extractor = load_wavlm("cuda")
    trim = make_silero_trim()
    clips = _load_clips()
    return {
        "gpu": torch.cuda.get_device_name(0),
        "sentences_as_phrases": _sentence_pairs(model, extractor, trim),
        "pipeline_check": _pipeline_check(model, extractor),
        "vad_segments_layer6": _speech_segments(clips, 6, model, extractor),
        "speed_cropped_2s_templates": _timing(model, extractor, trim, 2.0),
        "speed_full_length_templates": _timing(model, extractor, trim, None),
    }


@app.local_entrypoint()
def main() -> None:
    """Runs the evaluation on Modal and prints the numbers."""
    print(json.dumps(run_evaluation.remote(), indent=2))
