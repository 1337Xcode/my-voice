"""Putting lip frames and audio on one clock (EXP-SPEC 4.3 and 5.1): a 60 s frame ring and the audio clock."""

from collections import deque
from statistics import median

from voice.audio.pcm import SAMPLE_RATE
from voice.lips.frames import LipFrame

# 60 seconds at 25 frames a second.
RING_FRAMES = 60 * 25
# The app reports its audio clock once a second; the last half minute is plenty to fit.
CLOCK_POINTS = 30
MS_PER_SAMPLE = 1000 / SAMPLE_RATE


class FrameRing:
    """The session's last 60 seconds of frames, in device-time order."""

    def __init__(self, size: int = RING_FRAMES):
        self.frames: deque[LipFrame] = deque(maxlen=size)

    def add(self, frame: LipFrame) -> None:
        # JPEG encoding can finish a frame or two out of order; keep the ring sorted by time.
        if self.frames and frame.device_ms < self.frames[-1].device_ms:
            items = sorted([*self.frames, frame], key=lambda f: f.device_ms)
            self.frames.clear()
            self.frames.extend(items)
        else:
            self.frames.append(frame)

    def between(self, start_ms: float, end_ms: float) -> list[LipFrame]:
        """Frames with start_ms <= device time < end_ms."""
        return [f for f in self.frames if start_ms <= f.device_ms < end_ms]

    def clear(self) -> None:
        self.frames.clear()


class AudioClock:
    """Maps the session's audio sample count to the device clock, from the app's `audio_clock` reports.

    Each report says "n samples had been sent at device time t". Sample k was captured at t - (n - k) / 16 ms; the
    median over recent reports absorbs network and scheduling jitter. Constant capture latency is left in, and the
    sync check (4.4) measures it as the device's offset.
    """

    def __init__(self):
        self.points: deque[tuple[int, float]] = deque(maxlen=CLOCK_POINTS)

    def report(self, samples: int, device_ms: float) -> None:
        self.points.append((samples, device_ms))

    def ready(self) -> bool:
        return bool(self.points)

    def device_ms(self, sample: int) -> float | None:
        """Device time of session sample `sample`, or None before the first report."""
        if not self.points:
            return None
        origin = median(t - n * MS_PER_SAMPLE for n, t in self.points)
        return origin + sample * MS_PER_SAMPLE
