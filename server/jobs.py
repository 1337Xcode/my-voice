"""Modal app for the batch jobs: babble bank, prompts, team import, ASR evaluation, adapter registration and training.

Deployed separately as `my-voice-jobs` (`npm run deploy` deploys both); the server starts training with
`modal.Function.from_name("my-voice-jobs", "train_job")`. Run one from `server/`:
`modal run jobs.py::train --speaker P1` (also build_noise_bank, build_prompts, import_team, eval_asr, register_adapter).
"""

import logging
import time
from pathlib import Path

import modal

# The full turn (recogniser, phrase matcher, gate) needs the serving image, which also bakes WavLM.
from main import serve_image

# Containers import this module, which imports main, so both images carry main.py.
pipeline_image = serve_image.add_local_python_source("main")

# Training GPU: L40S (bf16 ~2.9x an A10G's tensor throughput and 48 GB, so batch 8 micro-steps fit), keeping 300 clips under 6 minutes.
TRAIN_GPU = "L40S"
# Scoring runs on the serving GPU type: beam search in fp16 differs slightly between GPU types, and the
# promotion margin is half a point, so a version is judged exactly as serving will decode it.
EVAL_GPU = "A10G"
JOB_TIMEOUT_S = 30 * 60
HF_HOME = "/root/hf"

data_volume = modal.Volume.from_name("speech-data", create_if_missing=True)
models_volume = modal.Volume.from_name("speech-models", create_if_missing=True)
secret = modal.Secret.from_name("my-voice-env")
VOLUMES = {"/data": data_volume, "/models": models_volume}


def download_whisper() -> None:
    """Bakes the base model into the image, so jobs start without a download."""
    from huggingface_hub import snapshot_download

    snapshot_download("openai/whisper-large-v3-turbo", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"])


# The same pins as the serving image, so evaluation decodes exactly as serving does.
jobs_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install(
        "torch==2.15.*", "transformers==5.22.*", "peft==0.21.*", "accelerate==1.15.*", "soundfile==0.14.*",
        "scipy==1.18.*", "numpy==2.*", "httpx==0.28.*", "pydantic==2.*", "huggingface_hub", "jiwer==4.*", "pyloudnorm==0.1.*",
    )
    .env({"HF_HOME": HF_HOME, "TOKENIZERS_PARALLELISM": "false"})
    .run_function(download_whisper)
    .env({"SPEECH_DATA_ROOT": "/data", "SPEECH_MODELS_ROOT": "/models", "SPEECH_ASSETS_ROOT": "/assets", "HF_HUB_OFFLINE": "1"})
    .add_local_dir("assets", "/assets")
    .add_local_python_source("voice", "main")
)

app = modal.App("my-voice-jobs")


def start_job() -> None:
    """Common job start: logging on, and the latest committed state of both volumes."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    data_volume.reload()
    models_volume.reload()


def commit() -> None:
    """Persists this job's writes to both volumes."""
    data_volume.commit()
    models_volume.commit()


def whisper_loader():
    """Loads the serving recogniser on this container's GPU."""
    from voice.asr.whisper import load_whisper

    return load_whisper("cuda")


@app.function(image=jobs_image, volumes=VOLUMES, timeout=JOB_TIMEOUT_S, cpu=4, memory=8192)
def build_noise_bank_job() -> dict:
    """Spec 9.4: downloads LibriSpeech dev-clean and writes 20 babble tracks to _shared/noise/babble/."""
    import tempfile

    from voice.training.babble import build_babble_bank, download_librispeech

    start_job()
    with tempfile.TemporaryDirectory() as workdir:
        manifest = build_babble_bank(download_librispeech(Path(workdir)))
    commit()
    return {"tracks": len(manifest["tracks"]), "seconds_each": manifest["seconds"]}


@app.function(image=jobs_image, volumes=VOLUMES, timeout=300)
def build_prompts_job() -> dict:
    """Spec 9.5: fetches the 72 Harvard lists and writes them and the default phrases to _shared/prompts/."""
    from voice.training.prompts import build_prompts

    start_job()
    counts = build_prompts()
    commit()
    return counts


@app.function(image=jobs_image, volumes=VOLUMES, timeout=JOB_TIMEOUT_S, cpu=4)
def import_team_job(speaker: str, staged: str = "") -> dict:
    """Spec 12.3: imports the team's clips (the volume layout, or a staged hack-speech folder), re-freezes the test set
    and writes the synthetic babble test audio."""
    import shutil
    from dataclasses import asdict

    from voice.clips.team_import import import_team_folder
    from voice.storage import DATA_ROOT, speaker_dir
    from voice.training.improve import refreeze_test_set

    start_job()
    root = DATA_ROOT / staged if staged else speaker_dir(speaker)
    search = [root / "raw", root / "practice"] if staged else [root / "incoming", root / "wav", root / "raw"]
    report = asdict(import_team_folder(speaker, root, search))
    frozen = refreeze_test_set(speaker)
    report["test_set"] = {"id": frozen.id, "clips": {condition: len(ids) for condition, ids in frozen.conditions.items()}}
    if staged:
        shutil.rmtree(root)
    commit()
    return report


@app.function(image=jobs_image, volumes=VOLUMES, secrets=[secret], gpu=EVAL_GPU, timeout=JOB_TIMEOUT_S)
def eval_asr_job(speaker: str) -> dict:
    """Spec 12.3 eval_asr: WER per version per condition, plus stock, on the frozen test set."""
    from voice.evaluation.asr_eval import eval_asr

    start_job()
    summary = eval_asr(whisper_loader(), speaker)
    commit()
    return summary


@app.function(image=jobs_image, volumes=VOLUMES, secrets=[secret], gpu=EVAL_GPU, timeout=JOB_TIMEOUT_S)
def register_adapter_job(name: str, speaker: str) -> dict:
    """Spec 12.3 register_adapter: adopts speech-models/<name> as a new version, promoted only if better."""
    from voice.training.improve import register_adapter

    start_job()
    return register_adapter(speaker, name, whisper_loader, commit)


@app.function(image=jobs_image, volumes=VOLUMES, secrets=[secret], gpu=EVAL_GPU, timeout=JOB_TIMEOUT_S)
def decide_version_job(speaker: str, name: str) -> dict:
    """Scores a freshly trained version on the serving GPU type and promotes it if better (spec 9.3)."""
    from voice.training.improve import decide_version

    start_job()
    return decide_version(speaker, name, whisper_loader, commit)


@app.function(image=jobs_image, volumes=VOLUMES, secrets=[secret], gpu=TRAIN_GPU, timeout=JOB_TIMEOUT_S, max_containers=1)
def train_job(speaker: str) -> dict:
    """Spec 9.3 Improve now: trains on the L40S, then scores on an A10G like serving, reporting progress in train_status.json."""
    from voice.training.improve import train_new_version
    from voice.training.registry import mark_failed, write_status

    start_job()
    started, name = time.time(), None
    try:
        name = train_new_version(speaker, commit)
        status = decide_version_job.remote(speaker, name)
    except Exception as error:
        models_volume.reload()
        if name:
            mark_failed(speaker, name, str(error))
        write_status(speaker, "failed", f"Training stopped: {error}")
        commit()
        raise
    return {**status, "job_seconds": round(time.time() - started, 1)}


@app.function(image=pipeline_image, volumes=VOLUMES, secrets=[secret], gpu=EVAL_GPU, timeout=JOB_TIMEOUT_S)
def eval_pipeline_job(speaker: str, providers: list[str]) -> dict:
    """Spec 15.4: replays the frozen test set through recognisers and gate per provider and calibrates speak_threshold."""
    import asyncio

    from voice.evaluation.pipeline_eval import eval_pipeline
    from voice.phrases.live import load_live_matchers
    from voice.runtime import Runtime

    start_job()
    runtime = Runtime.load(device="cuda")
    runtime.ensure_adapter(speaker)
    summary = asyncio.run(eval_pipeline(runtime.whisper, runtime.phrases or load_live_matchers("cuda"), speaker, providers))
    commit()
    return summary


@app.local_entrypoint()
def eval_pipeline(speaker: str = "P1", providers: str = "jev,openai"):
    """Replays his test clips through the whole turn and prints the calibration per decision provider."""
    for provider, result in eval_pipeline_job.remote(speaker, providers.split(",")).items():
        print(provider, {k: v for k, v in result.items() if k != "curve"})


@app.local_entrypoint()
def build_noise_bank():
    """Builds the babble bank."""
    print(build_noise_bank_job.remote())


@app.local_entrypoint()
def build_prompts():
    """Stores the Harvard lists and default phrases."""
    print(build_prompts_job.remote())


@app.local_entrypoint()
def import_team(speaker: str = "P1", folder: str = ""):
    """Imports the team's clips from the volume, or from a local hack-speech folder (--folder), then evaluates."""
    staged = ""
    if folder:
        staged = f"{speaker}/import/{int(time.time())}"
        with data_volume.batch_upload(force=True) as batch:
            batch.put_directory(folder, f"/{staged}")
    print(import_team_job.remote(speaker, staged))
    print(eval_asr_job.remote(speaker))


@app.local_entrypoint()
def eval_asr(speaker: str = "P1"):
    """Scores stock Whisper and every registered version."""
    print(eval_asr_job.remote(speaker))


@app.local_entrypoint()
def register_adapter(name: str, speaker: str = "P1"):
    """Registers a teammate's adapter from the speech-models volume root."""
    print(register_adapter_job.remote(name, speaker))


@app.local_entrypoint()
def decide(name: str, speaker: str = "P1"):
    """Re-runs scoring and the promotion decision for an already trained version (after a failed scoring step)."""
    print(decide_version_job.remote(speaker, name))


@app.local_entrypoint()
def train(speaker: str = "P1"):
    """Same as Improve now."""
    print(train_job.remote(speaker))
