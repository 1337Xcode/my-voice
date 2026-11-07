"""The clear voice: ElevenLabs Flash v2.5 streaming TTS with an on-volume cache (spec 8.9)."""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from voice.config import ASSETS_ROOT, require
from voice.storage import speaker_dir

MODEL_ID = "eleven_flash_v2_5"
APP_FORMAT = "mp3_44100_128"
CALL_FORMAT = "ulaw_8000"
API_ROOT = "https://api.elevenlabs.io"
TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)
RETRY_DELAYS_S = (0.3, 0.8)


class VoiceError(RuntimeError):
    """A plain-language TTS failure the app can show."""


@dataclass
class Speech:
    """Synthesised audio and how long it took."""

    audio: bytes
    format: str
    first_byte_ms: float
    total_ms: float
    cached: bool


def voices() -> dict:
    """The voices he can choose from, and the default (server/assets/voices.json)."""
    return json.loads((ASSETS_ROOT / "voices.json").read_text(encoding="utf-8"))


def cache_path(speaker: str, voice_id: str, fmt: str, text: str) -> Path:
    """Where the audio for (voice, format, text) is cached on the volume."""
    digest = hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:20]
    extension = "mp3" if fmt.startswith("mp3") else "ulaw"
    return speaker_dir(speaker) / "tts" / voice_id / fmt / f"{digest}.{extension}"


async def synthesise(client: httpx.AsyncClient, speaker: str, text: str, voice_id: str, fmt: str = APP_FORMAT, speed: float = 1.0) -> Speech:
    """Returns cached audio, or streams it from ElevenLabs and caches it."""
    path = cache_path(speaker, voice_id, fmt, f"{speed:.2f}|{text}")
    if path.exists():
        return Speech(path.read_bytes(), fmt, 0.0, 0.0, True)
    speech = await _stream(client, text, voice_id, fmt, speed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(speech.audio)
    return speech


async def _stream(client: httpx.AsyncClient, text: str, voice_id: str, fmt: str, speed: float) -> Speech:
    """One streaming request, retried twice on 429 and 5xx."""
    key = require("ELEVENLABS_API_KEY", "the voice")
    body = {"text": text, "model_id": MODEL_ID, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": max(0.7, min(1.2, speed))}}
    url = f"{API_ROOT}/v1/text-to-speech/{voice_id}/stream"
    for attempt in range(len(RETRY_DELAYS_S) + 1):
        started = time.perf_counter()
        async with client.stream("POST", url, params={"output_format": fmt}, headers={"xi-api-key": key}, json=body, timeout=TIMEOUT) as response:
            if response.status_code == 200:
                return await _collect(response, fmt, started)
            detail = (await response.aread()).decode("utf-8", "replace")[:300]
        if response.status_code in (401, 403):
            raise VoiceError("The voice service refused the key. Check ELEVENLABS_API_KEY.")
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < len(RETRY_DELAYS_S):
                await asyncio.sleep(RETRY_DELAYS_S[attempt])
                continue
        raise VoiceError(f"The voice service failed ({response.status_code}): {detail}")
    raise VoiceError("The voice service is busy. Try again.")


async def _collect(response: httpx.Response, fmt: str, started: float) -> Speech:
    """Reads the stream, noting when the first byte arrived."""
    chunks: list[bytes] = []
    first_byte_ms = 0.0
    async for chunk in response.aiter_bytes():
        if not chunks:
            first_byte_ms = (time.perf_counter() - started) * 1000
        chunks.append(chunk)
    audio = b"".join(chunks)
    if not audio:
        raise VoiceError("The voice service returned no audio. Try again.")
    return Speech(audio, fmt, round(first_byte_ms, 1), round((time.perf_counter() - started) * 1000, 1), False)
