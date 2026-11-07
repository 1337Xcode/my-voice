"""Streaming end-of-speech detection with Silero VAD over a turn's incoming frames (spec 8.2)."""

from dataclasses import dataclass, field

import numpy as np

from voice.audio.pcm import SAMPLE_RATE

# Silero VAD scores exactly 512-sample windows at 16 kHz (32 ms each).
WINDOW_SAMPLES = 512
WINDOW_MS = WINDOW_SAMPLES * 1000 / SAMPLE_RATE
SPEECH_PROBABILITY = 0.5
MIN_SPEECH_MS = 250
MAX_TURN_S = 30.0


@dataclass
class EndpointState:
    """What the VAD has seen so far in one turn."""

    speech_ms: float = 0.0
    trailing_silence_ms: float = 0.0
    heard_speech: bool = False
    first_speech_sample: int | None = None
    last_speech_sample: int | None = None


@dataclass
class TurnAudio:
    """One turn's audio buffer, scored by the VAD window by window as frames arrive."""

    vad_model: object
    silence_ms: int
    samples: list[np.ndarray] = field(default_factory=list)
    total: int = 0
    scored_upto: int = 0
    state: EndpointState = field(default_factory=EndpointState)
    pending: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))

    def __post_init__(self):
        self.vad_model.reset_states()

    def add(self, audio: np.ndarray) -> bool:
        """Adds samples and returns True when the turn should end (silence after speech, or the 30 s cap)."""
        import torch

        self.samples.append(audio)
        self.total += audio.size
        self.pending = np.concatenate([self.pending, audio])
        while self.pending.size >= WINDOW_SAMPLES:
            window, self.pending = self.pending[:WINDOW_SAMPLES], self.pending[WINDOW_SAMPLES:]
            probability = float(self.vad_model(torch.from_numpy(window.copy()), SAMPLE_RATE).item())
            self._score(probability)
        return self.ended_by_silence() or self.total >= MAX_TURN_S * SAMPLE_RATE

    def _score(self, probability: float) -> None:
        state = self.state
        start = self.scored_upto
        self.scored_upto += WINDOW_SAMPLES
        if probability >= SPEECH_PROBABILITY:
            state.speech_ms += WINDOW_MS
            state.trailing_silence_ms = 0.0
            state.heard_speech = True
            state.first_speech_sample = start if state.first_speech_sample is None else state.first_speech_sample
            state.last_speech_sample = self.scored_upto
        elif state.heard_speech:
            state.trailing_silence_ms += WINDOW_MS

    def ended_by_silence(self) -> bool:
        """True once enough speech was heard and it has been followed by the configured silence."""
        return self.state.speech_ms >= MIN_SPEECH_MS and self.state.trailing_silence_ms >= self.silence_ms

    def audio(self) -> np.ndarray:
        """The whole turn as one array."""
        return np.concatenate(self.samples) if self.samples else np.zeros(0, dtype=np.float32)

    def speech_audio(self, pad_s: float = 0.2) -> np.ndarray:
        """The turn trimmed to its speech, keeping `pad_s` of context each side (Whisper hallucinates on long silence)."""
        whole = self.audio()
        first, last = self.state.first_speech_sample, self.state.last_speech_sample
        if first is None or last is None:
            return whole
        pad = int(pad_s * SAMPLE_RATE)
        return whole[max(0, first - pad) : min(whole.size, last + pad)]

    def too_short(self) -> bool:
        """True when less than 250 ms of speech was detected (spec 8.2)."""
        return self.state.speech_ms < MIN_SPEECH_MS
