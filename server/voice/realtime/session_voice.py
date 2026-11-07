"""A session's streamed voice (EXP R1): his sentences go to the app as `audio_chunk` messages while they are made."""

import asyncio
import base64
import logging
from typing import TYPE_CHECKING

from voice.config import MissingKey
from voice.realtime.voice_stream import VoiceStream, sample_rate_of
from voice.tts.elevenlabs import VoiceError, cache_path
from voice.turns.record import TurnRecord, now_ms

if TYPE_CHECKING:
    from voice.session import Session

log = logging.getLogger("voice.realtime")

# Raw 16-bit PCM plays straight into the browser's Web Audio with no decoding step.
APP_STREAM_FORMAT = "pcm_24000"
# ElevenLabs sends about a second of audio per chunk; passing it on in quarter seconds gets the first sound out
# sooner on a phone's connection (12000 bytes = 0.25 s of 24 kHz 16-bit mono).
PIECE_BYTES = 12_000


class RealtimeVoice:
    """Keeps one connection in his voice and speed, reopened when he changes either."""

    def __init__(self, session: "Session"):
        self.session = session
        self.stream: VoiceStream | None = None

    def _current(self) -> VoiceStream:
        voice_id = self.session.voice_id()
        speed = float(self.session.settings()["speech_rate"])
        if self.stream is None or not self.stream.matches(voice_id, APP_STREAM_FORMAT, speed):
            if self.stream is not None:
                self.session.spawn(self.stream.close())
            self.stream = VoiceStream(voice_id, APP_STREAM_FORMAT, speed)
        return self.stream

    async def warm(self) -> None:
        """Opens the connection ahead of the first sentence, so it starts in about a tenth of a second."""
        try:
            await self._current().open()
        except (VoiceError, MissingKey) as error:
            log.warning("streamed voice did not warm: %s", error)

    async def speak(self, text: str, turn_id: str, record: TurnRecord | None) -> str:
        """Streams one sentence; returns "spoken", "no_sound" (nothing reached him) or "cut_off".

        Steps: a sentence he has said before plays from the cache at once; otherwise it streams from ElevenLabs in
        quarter-second pieces, and the whole sentence is cached when it completes.
        """
        started_ms = now_ms()
        stream = self._current()
        cached = cache_path(self.session.speaker, stream.voice_id, APP_STREAM_FORMAT, f"{stream.speed:.2f}|{text}").with_suffix(".pcm")
        pieces = _Pieces(self.session, turn_id)
        if await asyncio.to_thread(cached.exists):
            audio = await asyncio.to_thread(cached.read_bytes)
            await pieces.send(audio, final=True)
            _note(record, started_ms, {"first_chunk_ms": 0.0, "total_ms": 0.0, "chunks": pieces.seq, "cached": True})
            return "spoken"
        heard: list[bytes] = []

        async def on_chunk(audio: bytes, _seq: int, final: bool) -> None:
            heard.append(audio)
            await pieces.send(audio, final)

        try:
            result = await stream.speak(text, on_chunk)
        except (VoiceError, MissingKey) as error:
            if record is not None:
                record.errors.append(f"realtime voice: {error}")
            return "cut_off" if pieces.sent_audio else "no_sound"
        await asyncio.to_thread(_write, cached, b"".join(heard))
        _note(record, started_ms, {"first_chunk_ms": result.first_chunk_ms, "total_ms": result.total_ms, "chunks": pieces.seq, "cached": False})
        return "spoken"

    async def close(self) -> None:
        """Closes the connection (experiment switched off, or the app went away)."""
        stream, self.stream = self.stream, None
        if stream is not None:
            await asyncio.shield(stream.close())


class _Pieces:
    """Sends a sentence's audio to the app as numbered `audio_chunk` messages of at most PIECE_BYTES each."""

    def __init__(self, session: "Session", turn_id: str):
        self.session = session
        self.turn_id = turn_id
        self.seq = 0
        self.sent_audio = False

    async def send(self, audio: bytes, final: bool) -> None:
        """Splits `audio` into pieces; the last piece carries `final` (an empty one when there is no audio)."""
        parts = [audio[i : i + PIECE_BYTES] for i in range(0, len(audio), PIECE_BYTES)] or [b""]
        for index, part in enumerate(parts):
            self.sent_audio = self.sent_audio or bool(part)
            await self.session.send({"type": "audio_chunk", "turn_id": self.turn_id, "seq": self.seq, "format": APP_STREAM_FORMAT,
                                     "sample_rate": sample_rate_of(APP_STREAM_FORMAT), "data": base64.b64encode(part).decode("ascii"),
                                     "final": final and index == len(parts) - 1})
            self.seq += 1


def _note(record: TurnRecord | None, started_ms: int, stats: dict) -> None:
    """Puts the sentence's voice timings on the turn record."""
    if record is None:
        return
    record.t_tts_first_byte = started_ms + int(stats["first_chunk_ms"])
    record.mark("t_tts_done")
    record.exp["realtime_voice"] = stats


def _write(path, audio: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
