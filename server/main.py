"""The Modal app: the GPU speech server, its volumes, secret and image (spec section 4).

Deploy from the repo root with `npm run deploy`, which syncs .env into the Modal secret first.
"""

import os

import modal

APP_NAME = "my-voice"
SECRET_NAME = "my-voice-env"
# Keeps one container always on for demo day; read on the developer machine at deploy time.
KEEP_WARM = os.environ.get("KEEP_WARM", "0") == "1"
SCALEDOWN_WINDOW_S = 15 * 60
# A WebSocket session is one input; this lets a session run for an hour before the app reconnects.
SESSION_TIMEOUT_S = 60 * 60
# Model weights are baked into the image here, so a cold start reads them from local disk.
HF_HOME = "/root/hf"

data_volume = modal.Volume.from_name("speech-data", create_if_missing=True)
models_volume = modal.Volume.from_name("speech-models", create_if_missing=True)
secret = modal.Secret.from_name(SECRET_NAME)


def download_models() -> None:
    """Fetches the recogniser, the phrase-matcher encoder and the VAD at image build time."""
    from huggingface_hub import snapshot_download
    from silero_vad import load_silero_vad

    snapshot_download("openai/whisper-large-v3-turbo", allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"])
    snapshot_download("microsoft/wavlm-base-plus", allow_patterns=["*.json", "*.bin", "*.safetensors"])
    snapshot_download("microsoft/wavlm-base-plus-sv", allow_patterns=["*.json", "*.bin", "*.safetensors"])
    load_silero_vad()


serve_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .uv_pip_install(
        "torch==2.15.*", "transformers==5.22.*", "peft==0.21.*", "accelerate==1.15.*", "silero-vad==6.2.*",
        "soundfile==0.14.*", "scipy==1.18.*", "numpy==2.*", "httpx==0.28.*", "fastapi[standard]==0.162.*",
        "pydantic==2.*", "huggingface_hub", "rapidfuzz==3.*", "jiwer==4.*",
    )
    .env({"HF_HOME": HF_HOME, "TOKENIZERS_PARALLELISM": "false"})
    .run_function(download_models)
    .env({"SPEECH_DATA_ROOT": "/data", "SPEECH_MODELS_ROOT": "/models", "SPEECH_ASSETS_ROOT": "/assets", "HF_HUB_OFFLINE": "1"})
    .add_local_dir("assets", "/assets")
    .add_local_python_source("voice")
)

app = modal.App(APP_NAME)


def commit_volumes() -> None:
    """Persists writes to both volumes so other containers (and the trainer) see them."""
    data_volume.commit()
    models_volume.commit()


def reload_models() -> None:
    """Picks up a newly promoted model. Only the models volume is reloaded while serving: a reload fails, or briefly
    hides files, while any file is open, and the data volume is in constant use by live turns."""
    models_volume.reload()


def read_committed(volume: str, path: str) -> bytes | None:
    """The latest committed copy of a file another container wrote, read through Modal's API without remounting."""
    import modal.exception

    target = data_volume if volume == "data" else models_volume
    try:
        return b"".join(target.read_file(path))
    except (FileNotFoundError, modal.exception.NotFoundError):
        return None


@app.cls(
    image=serve_image,
    gpu="A10G",
    volumes={"/data": data_volume, "/models": models_volume},
    secrets=[secret],
    max_containers=1,
    min_containers=1 if KEEP_WARM else 0,
    scaledown_window=SCALEDOWN_WINDOW_S,
    timeout=SESSION_TIMEOUT_S,
)
@modal.concurrent(max_inputs=32)
class Speech:
    """The single serving container: every WebSocket and route lands here."""

    @modal.enter()
    def load(self):
        import logging

        from voice.runtime import Runtime

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
        self.runtime = Runtime.load(device="cuda", commit=commit_volumes, reload=reload_models, read_committed=read_committed)

    @modal.exit()
    def flush(self):
        commit_volumes()

    @modal.asgi_app()
    def web(self):
        from voice.web import create_app

        return create_app(self.runtime)
