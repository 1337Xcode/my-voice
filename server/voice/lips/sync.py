"""The 10-second sync check (EXP-SPEC 4.4): he says "pa pa pa pa pa"; the lag between the audio bursts and his
lip openings is the device's constant audio-video offset."""

from dataclasses import dataclass

import numpy as np

from voice.audio.pcm import SAMPLE_RATE

HOP_MS = 10
MAX_LAG_MS = 500
# Below this correlation the lips and the audio don't agree well enough to trust the lag.
MIN_CORRELATION = 0.3
MIN_BURSTS = 3


@dataclass
class SyncResult:
    ok: bool
    offset_ms: float | None
    correlation: float
    bursts: int
    reason: str | None


def _zscore(x: np.ndarray) -> np.ndarray:
    spread = x.std()
    return (x - x.mean()) / spread if spread > 1e-9 else np.zeros_like(x)


def audio_envelope(audio: np.ndarray) -> np.ndarray:
    """RMS energy in 10 ms hops."""
    hop = SAMPLE_RATE * HOP_MS // 1000
    usable = audio[: audio.size - audio.size % hop]
    return np.sqrt((usable.reshape(-1, hop) ** 2).mean(axis=1)) if usable.size else np.zeros(0)


def count_bursts(envelope: np.ndarray) -> int:
    """Separate loud stretches: rising crossings of halfway between the quiet floor and the peaks."""
    if envelope.size == 0:
        return 0
    floor, peak = np.percentile(envelope, 20), np.percentile(envelope, 98)
    loud = envelope > floor + 0.5 * (peak - floor)
    return int(np.count_nonzero(loud[1:] & ~loud[:-1]) + int(loud[0]))


def lip_track(frame_ms: np.ndarray, opening: np.ndarray, start_ms: float, hops: int) -> np.ndarray:
    """His mouth opening resampled onto the audio's 10 ms grid, which starts at device time `start_ms`."""
    grid = start_ms + np.arange(hops) * HOP_MS
    return np.interp(grid, frame_ms, opening, left=opening[0], right=opening[-1])


def estimate_offset(audio: np.ndarray, audio_start_ms: float, frame_ms: np.ndarray, opening: np.ndarray) -> SyncResult:
    """The lag (ms) to add to a frame's device time to line it up with the audio; positive when video runs early."""
    envelope = audio_envelope(audio)
    bursts = count_bursts(envelope)
    if bursts < MIN_BURSTS:
        return SyncResult(False, None, 0.0, bursts, "I couldn't hear clear 'pa' sounds. Say them a little louder and try again.")
    if frame_ms.size < 25:
        return SyncResult(False, None, 0.0, bursts, "The camera didn't see your mouth for long enough. Check the phone's position and try again.")
    lips = _zscore(lip_track(frame_ms, opening, audio_start_ms, envelope.size))
    sound = _zscore(envelope)
    best_lag, best = 0, -1.0
    for lag in range(-MAX_LAG_MS // HOP_MS, MAX_LAG_MS // HOP_MS + 1):
        # Shift the lips by `lag` hops: lips[i - lag] lines up with sound[i].
        a, b = (sound[lag:], lips[: lips.size - lag]) if lag >= 0 else (sound[:lag], lips[-lag:])
        if a.size < 50:
            continue
        r = float(np.mean(a * b))
        if r > best:
            best_lag, best = lag, r
    if best < MIN_CORRELATION:
        return SyncResult(False, None, round(best, 3), bursts, "Your lips and the sound didn't line up clearly. Face the phone and try again.")
    return SyncResult(True, float(best_lag * HOP_MS), round(best, 3), bursts, None)
