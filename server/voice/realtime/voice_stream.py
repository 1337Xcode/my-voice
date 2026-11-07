"""Streamed voice (EXP R1): one long-lived ElevenLabs multi-stream-input connection, one context per sentence.

The multi-context endpoint is used instead of `/stream-input` because only it marks the end of each sentence
(`isFinal` per context); on `/stream-input` the end only comes when the socket closes (docs/DECISIONS.md).
"""

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import websockets

from voice.config import require
from voice.tts.elevenlabs import MODEL_ID, VoiceError

log = logging.getLogger("voice.realtime")

URL = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/multi-stream-input"
# The longest idle time the endpoint allows; a keepalive inside it keeps the connection warm while the app is open.
INACTIVITY_TIMEOUT_S = 180
KEEPALIVE_EVERY_S = 60
CONNECT_TIMEOUT_S = 5.0
FIRST_CHUNK_TIMEOUT_S = 5.0
SENTENCE_TIMEOUT_S = 20.0
# Smaller first chunks start the sound sooner; these are ElevenLabs' own defaults.
CHUNK_SCHEDULE = [120, 160, 250, 290]

OnChunk = Callable[[bytes, int, bool], Awaitable[None]]


@dataclass
class Streamed:
    """How one sentence went: ms from sending the text to the first audio, and to its end."""

    first_chunk_ms: float
    total_ms: float
    chunks: int
    audio_bytes: int


def sample_rate_of(fmt: str) -> int:
    """`pcm_24000` → 24000, `ulaw_8000` → 8000."""
    return int(fmt.rsplit("_", 1)[1])


class VoiceStream:
    """A voice connection in one format and voice; sentences are spoken one at a time, in order."""

    def __init__(self, voice_id: str, fmt: str, speed: float):
        self.voice_id = voice_id
        self.fmt = fmt
        self.speed = max(0.7, min(1.2, speed))
        self.ws = None
        self.reader: asyncio.Task | None = None
        self.keepalive: asyncio.Task | None = None
        self.queues: dict[str, asyncio.Queue] = {}
        self.lock = asyncio.Lock()
        self.count = 0

    def matches(self, voice_id: str, fmt: str, speed: float) -> bool:
        """True when this connection already speaks in this voice, format and speed."""
        return self.voice_id == voice_id and self.fmt == fmt and abs(self.speed - max(0.7, min(1.2, speed))) < 1e-3

    async def open(self) -> None:
        """Connects (once) and starts reading; 401/403 means the key is wrong."""
        if self.ws is not None:
            return
        key = require("ELEVENLABS_API_KEY", "the streamed voice")
        url = (URL.format(voice_id=self.voice_id) + f"?model_id={MODEL_ID}&output_format={self.fmt}"
               f"&auto_mode=true&inactivity_timeout={INACTIVITY_TIMEOUT_S}")
        try:
            self.ws = await websockets.connect(url, additional_headers={"xi-api-key": key}, max_size=None, open_timeout=CONNECT_TIMEOUT_S)
        except websockets.InvalidStatus as error:
            status = error.response.status_code
            if status in (401, 403):
                raise VoiceError("The voice service refused the key. Check ELEVENLABS_API_KEY.") from error
            raise VoiceError(f"The streamed voice could not connect ({status}).") from error
        except (OSError, TimeoutError) as error:
            raise VoiceError("The streamed voice could not connect. Try again.") from error
        self.reader = asyncio.create_task(self._read())
        self.keepalive = asyncio.create_task(self._keep_alive())

    async def speak(self, text: str, on_chunk: OnChunk) -> Streamed:
        """Speaks one sentence, calling `on_chunk(audio, seq, final)` as audio arrives; the last call has final=True."""
        async with self.lock:
            try:
                return await self._speak(text, on_chunk)
            except websockets.ConnectionClosed:
                # The connection timed out or dropped between sentences: reconnect once and say it again.
                await self.close()
                return await self._speak(text, on_chunk)

    async def _speak(self, text: str, on_chunk: OnChunk) -> Streamed:
        await self.open()
        self.count += 1
        context = f"s{self.count}"
        queue: asyncio.Queue = asyncio.Queue()
        self.queues[context] = queue
        started = time.perf_counter()
        settings = {"stability": 0.5, "similarity_boost": 0.75, "speed": self.speed}
        try:
            await self.ws.send(json.dumps({"text": text.strip() + " ", "context_id": context, "flush": True, "voice_settings": settings,
                                           "generation_config": {"chunk_length_schedule": CHUNK_SCHEDULE}}))
            await self.ws.send(json.dumps({"context_id": context, "close_context": True}))
            return await self._forward(queue, started, on_chunk)
        finally:
            self.queues.pop(context, None)

    async def _forward(self, queue: asyncio.Queue, started: float, on_chunk: OnChunk) -> Streamed:
        """Passes each chunk on until the context's isFinal; times out if the audio stops coming."""
        seq, total, first_ms = 0, 0, None
        deadline = started + SENTENCE_TIMEOUT_S
        while True:
            wait = FIRST_CHUNK_TIMEOUT_S if first_ms is None else max(0.1, deadline - time.perf_counter())
            try:
                item = await asyncio.wait_for(queue.get(), wait)
            except TimeoutError as error:
                raise VoiceError("The voice stopped coming through. Tap Replay to try again.") from error
            if isinstance(item, BaseException):
                if first_ms is not None:
                    # Part of the sentence was already heard; saying it again from the start would repeat it.
                    raise VoiceError("The voice was cut off. Tap Replay to hear it again.") from item
                raise item
            if item is None:  # isFinal for this context
                await on_chunk(b"", seq, True)
                if first_ms is None:
                    raise VoiceError("The voice service returned no audio. Try again.")
                return Streamed(first_ms, round((time.perf_counter() - started) * 1000, 1), seq, total)
            if first_ms is None:
                first_ms = round((time.perf_counter() - started) * 1000, 1)
            total += len(item)
            await on_chunk(item, seq, False)
            seq += 1

    async def _read(self) -> None:
        """Routes every incoming message to its sentence's queue by context id."""
        try:
            async for raw in self.ws:
                message = json.loads(raw)
                queue = self.queues.get(message.get("contextId") or "")
                if queue is None:
                    if message.get("error") or message.get("message"):
                        log.warning("voice stream message without a sentence: %s", str(message)[:300])
                    continue
                if message.get("audio"):
                    queue.put_nowait(base64.b64decode(message["audio"]))
                if message.get("isFinal"):
                    queue.put_nowait(None)
        except websockets.ConnectionClosed as error:
            self._fail_waiting(error)
        except Exception as error:  # an unreadable message: fail the sentence in progress rather than hang it
            log.exception("voice stream reader failed")
            self._fail_waiting(VoiceError(f"The streamed voice failed: {error}"))
        finally:
            self.ws = None

    def _fail_waiting(self, error: BaseException) -> None:
        for queue in self.queues.values():
            queue.put_nowait(error)

    async def _keep_alive(self) -> None:
        """An empty text on its own context every minute keeps the idle connection from timing out."""
        while self.ws is not None:
            await asyncio.sleep(KEEPALIVE_EVERY_S)
            try:
                if self.ws is not None:
                    await self.ws.send(json.dumps({"text": "", "context_id": "keepalive"}))
            except websockets.ConnectionClosed:
                return

    async def close(self) -> None:
        """Closes the connection; the next sentence reconnects."""
        for task in (self.keepalive, self.reader):
            if task is not None:
                task.cancel()
        self.keepalive = self.reader = None
        ws, self.ws = self.ws, None
        if ws is not None:
            try:
                await ws.send(json.dumps({"close_socket": True}))
                await ws.close()
            except websockets.ConnectionClosed:
                pass
