"""Live captions of the other side of a call: VAD segments of their audio, transcribed in order with stock Whisper.

Their audio and the caption text live only in memory; nothing here touches the disk (spec 16).
"""

import asyncio
import logging
from typing import Awaitable, Callable

import numpy as np

from voice.audio.endpointing import TurnAudio
from voice.audio.pcm import SAMPLE_RATE

log = logging.getLogger("voice.calls.captions")

# A pause this long after speech closes a caption line.
SEGMENT_SILENCE_MS = 700
# A segment that has held no real speech for this long is dropped and restarted, so silence never piles up.
IDLE_RESTART_SAMPLES = 5 * SAMPLE_RATE
IDLE_SILENCE_MS = 1_000
# Phone lines carry noise blips; two speech windows in a row (64 ms) are needed to count as speech again.
CONFIRM_WINDOWS = 2
# A caption line longer than this ends at the next short pause, so captions keep flowing while they talk.
LONG_SEGMENT_SAMPLES = 8 * SAMPLE_RATE
SHORT_PAUSE_MS = 300


def drop_reason(recognition) -> str:
    """The guard that removed every hypothesis: no speech, a stock filler phrase, a repetition loop, or nothing heard."""
    from voice.asr.whisper import MAX_COMPRESSION_RATIO, MAX_NO_SPEECH_PROBABILITY, compression_ratio, filler_key

    if recognition.no_speech_probability > MAX_NO_SPEECH_PROBABILITY:
        return f"no_speech {recognition.no_speech_probability:.2f}"
    if not recognition.dropped:
        return "empty"
    text = recognition.dropped[0]
    if compression_ratio(text) > MAX_COMPRESSION_RATIO:
        return f"repetition loop (ratio {compression_ratio(text):.1f}, {len(text.split())} words)"
    return f"filler phrase ({len(filler_key(text).split())} words)" if filler_key(text) else "empty"


class CaptionStream:
    """Segments one continuous 16 kHz stream and reports each spoken line through `on_text`."""

    def __init__(self, runtime, on_text: Callable[[str], Awaitable[None]], on_error: Callable[[str], Awaitable[None]]):
        self.runtime = runtime
        self.on_text = on_text
        self.on_error = on_error
        self.vad_model = None
        self.segment: TurnAudio | None = None
        self.queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self.worker: asyncio.Task | None = None
        # Counts logged when the call ends, so a silent call and a deaf detector can be told apart.
        self.stats = {"seconds_in": 0.0, "speech_ms": 0.0, "segments": 0, "captions": 0, "dropped_by_guards": 0, "longest_pause_ms": 0.0}

    async def start(self) -> None:
        """Loads this stream's own VAD (it keeps state per stream) and starts the transcriber."""
        from silero_vad import load_silero_vad

        self.vad_model = await asyncio.to_thread(load_silero_vad)
        self.segment = self._new_segment()
        self.worker = asyncio.create_task(self._transcribe_in_order())

    def _new_segment(self) -> TurnAudio:
        return TurnAudio(vad_model=self.vad_model, silence_ms=SEGMENT_SILENCE_MS, confirm_windows=CONFIRM_WINDOWS)

    def add(self, audio: np.ndarray) -> None:
        """Adds 16 kHz float samples; a finished spoken segment is queued for transcription."""
        segment = self.segment
        if segment is None:
            return
        speech_before = segment.state.speech_ms
        ended = segment.add(audio) or self._long_and_pausing(segment)
        self.stats["longest_pause_ms"] = max(self.stats["longest_pause_ms"], segment.state.trailing_silence_ms)
        self.stats["seconds_in"] += audio.size / 16_000
        self.stats["speech_ms"] += segment.state.speech_ms - speech_before
        if ended or self._idle(segment):
            self.segment = self._new_segment()
            if ended and not segment.too_short():
                self.stats["segments"] += 1
                self.queue.put_nowait(segment.speech_audio())

    @staticmethod
    def _long_and_pausing(segment: TurnAudio) -> bool:
        """A long line ends at a short pause instead of waiting for a full one."""
        state = segment.state
        return segment.total >= LONG_SEGMENT_SAMPLES and state.heard_speech and state.trailing_silence_ms >= SHORT_PAUSE_MS

    @staticmethod
    def _idle(segment: TurnAudio) -> bool:
        """True for a long segment with no real speech yet (only silence, or a blip followed by silence)."""
        state = segment.state
        quiet = not state.heard_speech or state.trailing_silence_ms >= IDLE_SILENCE_MS
        return segment.too_short() and segment.total >= IDLE_RESTART_SAMPLES and quiet

    async def _transcribe_in_order(self) -> None:
        """Transcribes queued segments one at a time, so captions arrive in the order they were said."""
        while True:
            audio = await self.queue.get()
            try:
                text = await self._transcribe(audio)
            except Exception as error:  # A failed caption must not end the call; the error shows in its place.
                log.exception("caption failed")
                await self.on_error(f"A caption could not be made ({error}). The call is still going.")
                continue
            if text:
                self.stats["captions"] += 1
                await self.on_text(text)
            else:
                self.stats["dropped_by_guards"] += 1

    async def _transcribe(self, audio: np.ndarray) -> str:
        """The single best stock-Whisper text for one segment ("" when the guards drop it)."""
        whisper = self.runtime.whisper
        if whisper is None:
            raise RuntimeError("the recogniser is not loaded on this server")
        recognition = await asyncio.to_thread(whisper.nbest, audio, n=1, stock=True)
        if not recognition.hypotheses:
            # Why it was dropped, never what was said (their words are not kept, not even in logs).
            log.info("caption dropped: %s, %.1f s of audio", drop_reason(recognition), audio.size / SAMPLE_RATE)
        return recognition.hypotheses[0].text.strip() if recognition.hypotheses else ""

    def stop(self) -> None:
        """Stops transcribing; what they were saying as the call ended is still captioned."""
        segment, self.segment = self.segment, None
        if segment is not None and segment.state.heard_speech and not segment.too_short():
            self.stats["segments"] += 1
            self.queue.put_nowait(segment.speech_audio())
        log.info("caption stream stats: %s", {k: round(v, 1) for k, v in self.stats.items()})
        if self.worker is not None and not self.queue.empty():
            # Let the worker finish the last lines, then stop it.
            asyncio.get_running_loop().create_task(self._drain_then_stop())
            return
        self._cancel()

    async def _drain_then_stop(self) -> None:
        while not self.queue.empty():
            await asyncio.sleep(0.2)
        await asyncio.sleep(3)  # the last transcription is still running
        self._cancel()

    def _cancel(self) -> None:
        """Stops the transcriber and drops anything still queued."""
        if self.worker is not None:
            self.worker.cancel()
        while not self.queue.empty():
            self.queue.get_nowait()
