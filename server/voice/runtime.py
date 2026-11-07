"""Everything one serving container loads once and shares across sessions: models, HTTP client, settings."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from voice.config import MODELS_ROOT
from voice.storage import models_dir, read_json, speaker_dir, write_json

log = logging.getLogger("voice.runtime")

# Pipeline settings and their defaults (spec 8.2, 8.8, 11.7); the app changes them through /settings.
DEFAULT_SETTINGS = {
    "voice_id": None,
    "before_speaking": "speak",
    "speak_threshold": 0.85,
    "pick_threshold": 0.55,
    "endpoint_silence_ms": 900,
    "learn_from_conversations": False,
    "speech_rate": 1.0,
    "decide_provider": "jev",
}


@dataclass
class Runtime:
    """The container's loaded state."""

    whisper: object = None
    loaded_at: float = field(default_factory=time.time)
    load_seconds: float = 0.0
    http: httpx.AsyncClient | None = None
    commit_volumes: Callable[[], None] = lambda: None
    reload_volumes: Callable[[], None] = lambda: None
    sessions: set = field(default_factory=set)
    tasks: set = field(default_factory=set)

    @classmethod
    def load(cls, device: str | None = None, commit: Callable[[], None] | None = None, reload: Callable[[], None] | None = None) -> "Runtime":
        """Loads the recogniser (when a device is given) before the server accepts traffic."""
        started = time.time()
        runtime = cls(commit_volumes=commit or (lambda: None), reload_volumes=reload or (lambda: None))
        if device:
            from voice.asr.whisper import load_whisper

            runtime.whisper = load_whisper(device)
            runtime._warm_up()
        runtime.load_seconds = round(time.time() - started, 2)
        log.info("runtime loaded in %.1f s", runtime.load_seconds)
        return runtime

    def _warm_up(self) -> None:
        """Runs one decode so the first real turn doesn't pay CUDA initialisation."""
        import numpy as np

        self.whisper.nbest(np.zeros(16_000, dtype=np.float32))

    def client(self) -> httpx.AsyncClient:
        """One shared HTTP client (connection reuse cuts latency to the external APIs)."""
        if self.http is None:
            self.http = httpx.AsyncClient(http2=False, limits=httpx.Limits(max_keepalive_connections=20, keepalive_expiry=120))
        return self.http

    def registry_path(self, speaker: str) -> Path:
        """Where this speaker's model registry lives on the speech-models volume."""
        return models_dir(speaker) / "registry.json"

    def registry(self, speaker: str) -> dict:
        """The speaker's model registry, or an empty one."""
        return read_json(self.registry_path(speaker), {})

    def model_version(self, speaker: str) -> str:
        """The active model's name for this speaker, or 'stock' before his first model."""
        return self.registry(speaker).get("active") or "stock"

    def adapter_path(self, speaker: str) -> str | None:
        """The active adapter's folder, or None for the stock model."""
        registry = self.registry(speaker)
        active = registry.get("active")
        if not active:
            return None
        entry = registry.get("versions", {}).get(active, {})
        path = Path(entry.get("path") or (models_dir(speaker) / active))
        return str(path if path.is_absolute() else MODELS_ROOT / path)

    def ensure_adapter(self, speaker: str) -> str:
        """Swaps to the speaker's active adapter between turns if it changed; returns the version name."""
        path = self.adapter_path(speaker)
        if self.whisper is not None and self.whisper.adapter_path != path:
            self.whisper.set_adapter(path)
            log.info("adapter for %s is now %s", speaker, path or "stock")
        return self.model_version(speaker)

    def settings(self, speaker: str) -> dict:
        """The speaker's pipeline settings, defaults filled in."""
        return {**DEFAULT_SETTINGS, **read_json(speaker_dir(speaker) / "settings.json", {})}

    def save_settings(self, speaker: str, change: dict) -> dict:
        """Merges known keys into the speaker's settings and saves them."""
        merged = {**self.settings(speaker), **{k: v for k, v in change.items() if k in DEFAULT_SETTINGS}}
        write_json(speaker_dir(speaker) / "settings.json", merged)
        self.commit_volumes()
        return merged

    def background(self, coroutine) -> None:
        """Runs work after the response, keeping a reference so it isn't garbage-collected mid-run."""
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self._background_done)

    def _background_done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("background task failed", exc_info=task.exception())
        else:
            self.commit_volumes()

    async def broadcast(self, message: dict) -> None:
        """Sends a message to every connected app session (model updates, training status)."""
        for session in list(self.sessions):
            await session.send(message)
