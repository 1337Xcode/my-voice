"""Checks that phone-line audio splits into one caption line per spoken line (the bug from the first real call).

The audio is a real speech clip, said three times with pauses, with line noise and random blips added, then
put through 8 kHz mu-law and back exactly as a Twilio call delivers it.
"""

import asyncio
from pathlib import Path

import numpy as np
import pytest

from voice.audio.pcm import read_audio, resample
from voice.calls import mulaw
from voice.calls.captions import CaptionStream

FIXTURE = Path(__file__).parent / "fixtures" / "hello_caller.wav"


def phone_line(seed: int = 7) -> np.ndarray:
    """Three lines of speech 1.5 s apart, with hiss and 20 ms blips, through mu-law at 8 kHz; returned at 16 kHz."""
    rng = np.random.default_rng(seed)
    speech = read_audio(FIXTURE)
    gap = np.zeros(int(1.5 * 16_000), dtype=np.float32)
    audio = np.concatenate([gap, speech, gap, speech, gap, speech, gap])
    audio = audio + rng.normal(0, 0.004, audio.size).astype(np.float32)
    for start in rng.integers(0, audio.size - 320, size=40):
        audio[start : start + 320] += rng.normal(0, 0.05, 320).astype(np.float32)
    at_8k = resample(audio, 16_000, 8_000)
    line = mulaw.encode(np.clip(at_8k, -1, 1) * 32767)
    decoder = mulaw.PhoneAudioDecoder()  # the server's own path, fed 20 ms chunks as Twilio sends them
    return np.concatenate([decoder.decode(line[i : i + 160]) for i in range(0, len(line), 160)])


def test_each_spoken_line_on_a_noisy_phone_line_becomes_its_own_caption_segment():
    pytest.importorskip("silero_vad")

    async def run() -> CaptionStream:
        stream = CaptionStream(runtime=None, on_text=lambda text: asyncio.sleep(0), on_error=lambda text: asyncio.sleep(0))
        await stream.start()
        stream.worker.cancel()  # only segmentation is under test; nothing is transcribed
        audio = phone_line()
        for start in range(0, audio.size, 1_600):  # 100 ms frames, as the stream delivers them
            stream.add(audio[start : start + 1_600])
        return stream

    stream = asyncio.run(run())
    assert stream.stats["segments"] == 3, stream.stats
