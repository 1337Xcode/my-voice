"""Compares the transformers and CTranslate2 recognisers on the serving GPU: ms per clip, n-best agreement and WER.

Both backends decode every frozen test clip in every condition, plus all his labelled clips, with the stock model and
the active adapter, at each beam width. Parity bar: CT2 WER within 1 point of transformers everywhere, 2x faster.

Run: cd server && modal run scripts_ct2_bench.py --speaker P1 --beams 5,8
"""

import json
import time

import modal

from main import HF_HOME, data_volume, download_models, models_volume, secret

# The pip wheels' CUDA 12 cuBLAS, which CTranslate2 4.8 loads (torch 2.15 brings CUDA 13 libraries only).
CUBLAS_CU12_LIB = "/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib"

# The serving image (main.py) plus the three CTranslate2 lines main.py needs to switch backends.
ct2_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install(
        "torch==2.15.*", "transformers==5.22.*", "peft==0.21.*", "accelerate==1.15.*", "silero-vad==6.2.*",
        "soundfile==0.14.*", "scipy==1.18.*", "numpy==2.*", "httpx==0.28.*", "fastapi[standard]==0.162.*",
        "pydantic==2.*", "huggingface_hub", "rapidfuzz==3.*", "jiwer==4.*",
        "ctranslate2==4.8.*", "nvidia-cublas-cu12==12.*",
    )
    .env({"HF_HOME": HF_HOME, "TOKENIZERS_PARALLELISM": "false", "LD_LIBRARY_PATH": CUBLAS_CU12_LIB})
    .run_function(download_models)
    .run_commands(f"ct2-transformers-converter --model openai/whisper-large-v3-turbo --output_dir {HF_HOME}/ct2-whisper-large-v3-turbo --quantization float16")
    .env({"SPEECH_DATA_ROOT": "/data", "SPEECH_MODELS_ROOT": "/models", "SPEECH_ASSETS_ROOT": "/assets", "HF_HUB_OFFLINE": "1"})
    .add_local_dir("assets", "/assets")
    .add_local_python_source("voice")
)

app = modal.App("my-voice-ct2-bench")


def bench_clips(speaker: str) -> list[dict]:
    """Every frozen test clip per condition, plus every labelled clip with audio as condition "all_labelled"."""
    from voice.clips.records import audio_path, load_clips
    from voice.clips.selection import CONDITIONS, condition_audio, load_frozen_test_set

    frozen = load_frozen_test_set(speaker)
    clips = [{"condition": condition, "id": clip_id, "reference": frozen.texts[clip_id], "path": str(condition_audio(speaker, condition, clip_id))}
             for condition in CONDITIONS for clip_id in frozen.conditions.get(condition, [])]
    labelled = [clip for clip in load_clips(speaker).values() if clip.ok and clip.text and audio_path(speaker, clip.id).is_file()]
    return clips + [{"condition": "all_labelled", "id": clip.id, "reference": clip.text, "path": str(audio_path(speaker, clip.id))} for clip in labelled]


def decode_all(whisper, clips: list[dict], beams: int, stock: bool) -> list[dict]:
    """Decodes each clip's 5-best at one beam width, timing the whole call as serving sees it."""
    from pathlib import Path

    from voice.audio.pcm import read_audio

    rows = []
    for clip in clips:
        audio = read_audio(Path(clip["path"]))
        started = time.perf_counter()
        result = whisper.nbest(audio, n=5, stock=stock, beams=beams)
        rows.append({**clip, "seconds": round(audio.size / 16000, 2), "ms": round((time.perf_counter() - started) * 1000, 1),
                     "nbest": [[h.text, h.logprob, h.support] for h in result.hypotheses], "no_speech": result.no_speech_probability})
    return rows


@app.function(image=ct2_image, gpu="A10G", volumes={"/data": data_volume, "/models": models_volume}, secrets=[secret], timeout=3600)
def bench(speaker: str, beam_widths: list[int]) -> dict:
    """Decodes the bench clips with both backends, stock and active adapter, at each beam width; returns every row."""
    from voice.asr.ct2 import load_ct2_whisper, prepare_ct2
    from voice.asr.whisper import load_whisper
    from voice.config import MODELS_ROOT
    from voice.storage import read_json

    registry = read_json(MODELS_ROOT / speaker / "registry.json", {})
    adapter = str(MODELS_ROOT / registry["versions"][registry["active"]]["path"])
    started = time.perf_counter()
    prepare_ct2(adapter)
    prepare_seconds = round(time.perf_counter() - started, 1)
    models_volume.commit()
    clips = bench_clips(speaker)
    runs = {}
    for backend, loader in (("hf", load_whisper), ("ct2", load_ct2_whisper)):
        whisper = loader("cuda")
        whisper.set_adapter(adapter)
        for beams in beam_widths:
            decode_all(whisper, clips[:2], beams, stock=False)  # warm-up
            for model in ("stock", "adapter"):
                runs[f"{model}|{beams}|{backend}"] = decode_all(whisper, clips, beams, stock=model == "stock")
    return {"adapter": adapter, "prepare_seconds": prepare_seconds, "runs": runs}


def percentile(values: list[float], fraction: float) -> float:
    """The value at `fraction` of the sorted list (nearest rank)."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def agreement(hf_rows: list[dict], ct2_rows: list[dict]) -> dict:
    """How closely CT2's n-best matches transformers': same top-1, n-best overlap, score and no-speech gaps."""
    from voice.asr.whisper import filler_key

    same_top, overlaps, score_gaps, no_speech_gaps = 0, [], [], []
    for hf, ct2 in zip(hf_rows, ct2_rows):
        hf_keys, ct2_keys = [filler_key(h[0]) for h in hf["nbest"]], [filler_key(h[0]) for h in ct2["nbest"]]
        top_same = bool(hf_keys) and bool(ct2_keys) and hf_keys[0] == ct2_keys[0]
        same_top += top_same or (not hf_keys and not ct2_keys)
        overlaps.append(len(set(hf_keys) & set(ct2_keys)) / max(1, len(set(hf_keys) | set(ct2_keys))))
        if top_same:
            score_gaps.append(abs(hf["nbest"][0][1] - ct2["nbest"][0][1]))
        no_speech_gaps.append(abs(hf["no_speech"] - ct2["no_speech"]))
    return {"top1_same": f"{same_top}/{len(hf_rows)}", "nbest_overlap": round(sum(overlaps) / len(overlaps), 3),
            "top1_logprob_gap_max": round(max(score_gaps, default=0.0), 4), "no_speech_gap_max": round(max(no_speech_gaps), 4)}


def report(result: dict) -> None:
    """Prints WER and timing per condition for each model and beam width, and the agreement between backends."""
    from voice.evaluation.wer import wer_percent

    print(f"adapter {result['adapter']}; merge and convert took {result['prepare_seconds']} s")
    combos = sorted({key.rsplit("|", 1)[0] for key in result["runs"]})
    for combo in combos:
        hf_rows, ct2_rows = result["runs"][f"{combo}|hf"], result["runs"][f"{combo}|ct2"]
        print(f"\n== {combo.replace('|', ' beams=')}  agreement {agreement(hf_rows, ct2_rows)}")
        for condition in dict.fromkeys(row["condition"] for row in hf_rows):
            cells = []
            for rows in (hf_rows, ct2_rows):
                chosen = [row for row in rows if row["condition"] == condition]
                tops = [row["nbest"][0][0] if row["nbest"] else "" for row in chosen]
                ms = [row["ms"] for row in chosen]
                cells.append(f"WER {wer_percent([row['reference'] for row in chosen], tops):6.2f}  ms p50 {percentile(ms, 0.5):6.0f} p95 {percentile(ms, 0.95):6.0f}")
            print(f"  {condition:13s} n={len(chosen):3d}  HF {cells[0]}  |  CT2 {cells[1]}")


@app.local_entrypoint()
def main(speaker: str = "P1", beams: str = "5,8", out: str = ""):
    result = bench.remote(speaker, [int(width) for width in beams.split(",")])
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=1)
    report(result)
