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

data_volume = modal.Volume.from_name("speech-data", create_if_missing=True)
models_volume = modal.Volume.from_name("speech-models", create_if_missing=True)
secret = modal.Secret.from_name(SECRET_NAME)

serve_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("fastapi[standard]==0.162.*")
    .env({"SPEECH_DATA_ROOT": "/data", "SPEECH_MODELS_ROOT": "/models", "SPEECH_ASSETS_ROOT": "/assets"})
    .add_local_dir("assets", "/assets")
    .add_local_python_source("voice")
)

app = modal.App(APP_NAME)


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
        from voice.runtime import Runtime

        self.runtime = Runtime.load()

    @modal.asgi_app()
    def web(self):
        from voice.web import create_app

        return create_app(self.runtime)
