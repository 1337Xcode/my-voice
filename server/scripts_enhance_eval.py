"""Does any speech enhancer lower his word error?

Runs on a Modal A10G, the serving GPU type. Every enhancer cleans each frozen test clip, then the stock model and the
speaker's active personal adapter decode it, and WER is scored exactly as the Results screen scores it.

    cd server
    modal run scripts_enhance_eval.py::latency                    # milliseconds per enhancer for 6 s of audio
    modal run scripts_enhance_eval.py::evaluate --speaker P1      # WER table, written to ../.work/enhance_eval_P1.json
"""

import json
import zlib
from pathlib import Path

import modal
import numpy as np

# Restated from jobs.py rather than imported: jobs.py imports the whole serving app (main.py), which this evaluation does not need.
EVAL_GPU = "A10G"
HF_HOME = "/root/hf"
data_volume = modal.Volume.from_name("speech-data")
models_volume = modal.Volume.from_name("speech-models")
VOLUMES = {"/data": data_volume, "/models": models_volume}
secret = modal.Secret.from_name("my-voice-env")

ENHANCER_MODELS = "/root/enhancers"
CARGO_PATH = "/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
LATENCY_SECONDS = 6.0
LATENCY_REPEATS = 20
# The frozen babble mixes use one babble draw per clip; extra draws of the same clips (new seeds) give the babble cells more words.
EXTRA_DRAWS = 3
EXTRA_CONDITIONS = {"babble_5db": 5.0, "babble_0db": 0.0}
TIMEOUT_S = 55 * 60


def download_whisper() -> None:
    """Image build step: bakes the base model in, as the jobs image does."""
    from huggingface_hub import snapshot_download

    snapshot_download("openai/whisper-large-v3-turbo", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"])


def bake_enhancer_models() -> None:
    """Image build step: downloads DeepFilterNet 3 and the two SpeechBrain models so jobs start without a download."""
    import os

    os.environ["HF_HUB_OFFLINE"] = "0"
    from voice.audio.enhance import install_torchaudio_shim, load_enhancer

    install_torchaudio_shim()
    from df.enhance import init_df

    init_df(post_filter=False, log_level="WARNING")
    for name in ("metricgan_plus", "sepformer_wham16k"):
        load_enhancer(name, "cpu")


# The jobs image's pins, plus what enhancers need (keep in sync with jobs.jobs_image: Modal cannot add build steps after its local-file
# layers, so the image is restated rather than extended). torchaudio has no 2.15 build, so 2.11 is installed without dependencies:
# SpeechBrain only needs its Python side. DeepFilterNet's Rust core (deepfilterlib) has no Python 3.12 wheel, so it is built from source.
enhance_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "build-essential", "curl", "pkg-config", "git")
    .run_commands("curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal")
    .env({"PATH": CARGO_PATH, "ENHANCER_MODELS_ROOT": ENHANCER_MODELS, "HF_HOME": HF_HOME, "TOKENIZERS_PARALLELISM": "false"})
    .uv_pip_install(
        "torch==2.15.*", "transformers==5.22.*", "peft==0.21.*", "accelerate==1.15.*", "soundfile==0.14.*",
        "scipy==1.18.*", "numpy==2.*", "httpx==0.28.*", "pydantic==2.*", "huggingface_hub", "jiwer==4.*", "pyloudnorm==0.1.*",
    )
    .run_commands("pip install deepfilterlib==0.5.6")
    .uv_pip_install("noisereduce==3.0.3", "hyperpyyaml", "joblib", "sentencepiece", "tqdm", "loguru", "appdirs", "packaging", "sympy", "requests")
    .uv_pip_install("speechbrain==1.1.2", "torchaudio==2.11.1", "deepfilternet==0.5.6", extra_options="--no-deps")
    .run_function(download_whisper)
    .add_local_python_source("voice", copy=True)
    .run_function(bake_enhancer_models)
    .env({"SPEECH_DATA_ROOT": "/data", "SPEECH_MODELS_ROOT": "/models", "SPEECH_ASSETS_ROOT": "/assets", "HF_HUB_OFFLINE": "1"})
    .add_local_dir("assets", "/assets")
)

app = modal.App("my-voice-enhance-eval")


def load_clips(speaker: str, extra_draws: int) -> list[dict]:
    """Every test clip as {condition, id, reference, audio}: the frozen conditions, then extra babble draws of the same clips."""
    from voice.audio.pcm import read_audio
    from voice.clips.selection import CONDITIONS, condition_audio, load_frozen_test_set
    from voice.training.babble import babble_segment, load_babble_bank, mix_at_snr

    frozen = load_frozen_test_set(speaker)
    if frozen is None:
        raise FileNotFoundError(f"{speaker} has no frozen test set yet.")
    clips = [
        {"condition": condition, "id": clip_id, "reference": frozen.texts[clip_id], "audio": read_audio(condition_audio(speaker, condition, clip_id))}
        for condition in CONDITIONS
        for clip_id in frozen.conditions.get(condition, [])
    ]
    bank = load_babble_bank()
    for condition, snr_db in EXTRA_CONDITIONS.items():
        for clip_id in frozen.conditions["quiet"]:
            speech = read_audio(condition_audio(speaker, "quiet", clip_id))
            for draw in range(1, extra_draws + 1):
                rng = np.random.default_rng(zlib.crc32(f"{clip_id}|{condition}|extra{draw}".encode()))
                mixed = mix_at_snr(speech, babble_segment(bank, len(speech), rng), snr_db)
                clips.append({"condition": f"{condition}_extra", "id": f"{clip_id}#{draw}", "reference": frozen.texts[clip_id], "audio": mixed})
    return clips


def enhance_all(name: str, clips: list[dict]) -> tuple[list, float]:
    """Cleans every clip with one enhancer (None = leave as is); returns (audio per clip, mean ms per second of audio)."""
    import torch

    if name == "none":
        return [clip["audio"] for clip in clips], 0.0
    from voice.audio.enhance import load_enhancer

    enhancer = load_enhancer(name, "cuda")
    enhancer.process(clips[0]["audio"])  # warm-up
    audios, ms_per_second = [], []
    for clip in clips:
        cleaned = enhancer.process(clip["audio"])
        if not np.all(np.isfinite(cleaned)):
            raise ValueError(f"{name} produced non-finite samples on {clip['id']}.")
        audios.append(cleaned)
        ms_per_second.append(enhancer.last_ms / (clip["audio"].size / 16_000))
    del enhancer
    torch.cuda.empty_cache()
    return audios, float(np.mean(ms_per_second))


def decode_all(whisper, audios: list, stock: bool) -> list[str]:
    """The best Whisper text for each audio, with the stock model or the active adapter."""
    return [whisper.transcribe(audio, stock=stock) for audio in audios]


def score_cells(clips: list[dict], hypotheses: list[str]) -> dict:
    """Corpus WER and clip count per condition."""
    from voice.evaluation.wer import wer_percent

    cells = {}
    for condition in sorted({clip["condition"] for clip in clips}):
        rows = [(clip["reference"], text) for clip, text in zip(clips, hypotheses) if clip["condition"] == condition]
        cells[condition] = {"wer": wer_percent([ref for ref, _ in rows], [hyp for _, hyp in rows]), "n": len(rows)}
    return cells


def active_adapter(speaker: str) -> str | None:
    """The folder of the speaker's active personal adapter, or None when there is none."""
    from voice.config import MODELS_ROOT
    from voice.training.registry import load_registry

    registry = load_registry(speaker)
    entry = registry["versions"].get(registry.get("active") or "")
    return str(MODELS_ROOT / entry["path"]) if entry else None


@app.function(image=enhance_image, volumes=VOLUMES, secrets=[secret], gpu=EVAL_GPU, timeout=TIMEOUT_S)
def evaluate_job(speaker: str, names: list[str], extra_draws: int = EXTRA_DRAWS) -> dict:
    """WER per enhancer per condition for stock and personal Whisper; an enhancer that fails to load is reported, not hidden."""
    from voice.asr.whisper import load_whisper

    data_volume.reload()
    models_volume.reload()
    clips, adapter = load_clips(speaker, extra_draws), active_adapter(speaker)
    enhanced, latency, failures = {}, {}, {}
    for name in ["none", *names]:
        try:
            enhanced[name], latency[name] = enhance_all(name, clips)
        except Exception as error:  # a library that cannot run here is a finding, so it goes in the report
            failures[name] = f"{type(error).__name__}: {error}"
    whisper = load_whisper("cuda")
    results = {"stock": {}, "personal": {}}
    for name, audios in enhanced.items():
        results["stock"][name] = score_cells(clips, decode_all(whisper, audios, stock=True))
    repeat = decode_all(whisper, enhanced["none"], stock=True)
    results["stock_repeat_identical"] = repeat == decode_all(whisper, enhanced["none"], stock=True)
    if adapter:
        whisper.set_adapter(adapter)
        for name, audios in enhanced.items():
            results["personal"][name] = score_cells(clips, decode_all(whisper, audios, stock=False))
    return {"speaker": speaker, "adapter": adapter, "results": results, "ms_per_audio_second": latency, "failures": failures}


@app.function(image=enhance_image, volumes=VOLUMES, gpu=EVAL_GPU, timeout=TIMEOUT_S)
def latency_job(names: list[str], speaker: str = "P1") -> dict:
    """Median milliseconds to enhance 6 s of real speech on the A10G, per enhancer (GPU warmed up)."""
    import statistics

    from voice.audio.enhance import load_enhancer

    data_volume.reload()
    clips = load_clips(speaker, 0)
    audio = np.tile(clips[-1]["audio"], 8)[: int(LATENCY_SECONDS * 16_000)]
    report = {}
    for name in names:
        try:
            enhancer = load_enhancer(name, "cuda")
            for _ in range(3):
                enhancer.process(audio)
            times = []
            for _ in range(LATENCY_REPEATS):
                enhancer.process(audio)
                times.append(enhancer.last_ms)
            report[name] = {"median_ms": round(statistics.median(times), 1), "max_ms": round(max(times), 1)}
        except Exception as error:
            report[name] = {"error": f"{type(error).__name__}: {error}"}
    return report


def si_sdr_db(clean: np.ndarray, estimate: np.ndarray) -> float:
    """Scale-invariant signal-to-distortion ratio of `estimate` against `clean`, in dB (higher is cleaner)."""
    estimate = estimate - estimate.mean()
    clean = clean - clean.mean()
    target = (estimate @ clean) / (clean @ clean + 1e-12) * clean
    return float(10 * np.log10((target @ target + 1e-12) / (((estimate - target) ** 2).sum() + 1e-12)))


@app.function(image=enhance_image, volumes=VOLUMES, gpu=EVAL_GPU, timeout=TIMEOUT_S)
def sanity_job(speaker: str = "P1") -> dict:
    """Implementation check: does each enhancer raise SI-SDR against the clean clip? (WER can fall short of this, but it must not be negative.)"""
    from voice.audio.enhance import ENHANCER_NAMES, load_enhancer
    from voice.training.babble import mix_at_snr

    data_volume.reload()
    clips = [clip for clip in load_clips(speaker, 0) if clip["condition"] in ("quiet", "babble_5db", "babble_0db")]
    clean = {clip["id"]: clip["audio"] for clip in clips if clip["condition"] == "quiet"}
    rng = np.random.default_rng(0)
    clips += [{"condition": "white_10db", "id": clip_id, "audio": mix_at_snr(audio, rng.standard_normal(audio.size).astype(np.float32), 10.0)} for clip_id, audio in clean.items()]
    report = {"input": {}}
    for clip in clips:
        report["input"].setdefault(clip["condition"], []).append(si_sdr_db(clean[clip["id"]], clip["audio"]))
    for name in ENHANCER_NAMES:
        enhancer, scores = load_enhancer(name, "cuda"), {}
        for clip in clips:
            scores.setdefault(clip["condition"], []).append(si_sdr_db(clean[clip["id"]], enhancer.process(clip["audio"])))
        report[name] = scores
    return {name: {condition: round(float(np.mean(values)), 1) for condition, values in scores.items()} for name, scores in report.items()}


@app.local_entrypoint()
def sanity(speaker: str = "P1"):
    """Prints mean SI-SDR (dB against the clean clip) per enhancer and condition."""
    print(json.dumps(sanity_job.remote(speaker), indent=1))


def table(speaker_result: dict, model: str) -> str:
    """One markdown table (rows enhancers, columns conditions) for a model, cells 'WER (n clips)'."""
    rows = speaker_result["results"][model]
    conditions = sorted({condition for cells in rows.values() for condition in cells}, key=lambda c: (c.endswith("_extra"), c))
    lines = [f"| enhancer | {' | '.join(conditions)} | mean (frozen) |", "|---|" + "---|" * (len(conditions) + 1)]
    for name, cells in rows.items():
        frozen = [cells[c]["wer"] for c in cells if not c.endswith("_extra")]
        parts = [f"{cells[c]['wer']:.1f} ({cells[c]['n']})" if c in cells else "-" for c in conditions]
        lines.append(f"| {name} | {' | '.join(parts)} | {sum(frozen) / len(frozen):.1f} |")
    return "\n".join(lines)


@app.local_entrypoint()
def latency(names: str = ""):
    """Prints the per-enhancer latency for 6 s of audio."""
    from voice.audio.enhance import ENHANCER_NAMES

    print(json.dumps(latency_job.remote(names.split(",") if names else list(ENHANCER_NAMES)), indent=2))


@app.local_entrypoint()
def evaluate(speaker: str = "P1", names: str = "", extra_draws: int = EXTRA_DRAWS):
    """Runs the WER comparison, prints the tables and saves the full result under ../.work/."""
    from voice.audio.enhance import ENHANCER_NAMES

    result = evaluate_job.remote(speaker, names.split(",") if names else list(ENHANCER_NAMES), extra_draws)
    out = Path("..") / ".work" / f"enhance_eval_{speaker}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    for model in ("stock", "personal"):
        if result["results"][model]:
            print(f"\n{model} model ({speaker}, adapter {result['adapter']}):\n{table(result, model)}")
    print("\nms per audio second:", result["ms_per_audio_second"], "\nfailures:", result["failures"])
