"""Audio format conversion: 16-bit PCM frames, float arrays and 16 kHz mono WAV files."""

import io
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16_000
# Silence kept on each side of a clip when it is trimmed for storage (spec 7.1).
EDGE_SILENCE_S = 0.2


def pcm16_to_float(frame: bytes) -> np.ndarray:
    """Converts little-endian 16-bit PCM bytes to float32 samples in [-1, 1]."""
    usable = len(frame) - (len(frame) % 2)
    return np.frombuffer(frame[:usable], dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(audio: np.ndarray) -> bytes:
    """Converts float samples to little-endian 16-bit PCM bytes, clipping at full scale."""
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def peak_normalise(audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
    """Scales audio so its loudest sample reaches `peak`; silence is returned unchanged."""
    loudest = float(np.max(np.abs(audio))) if audio.size else 0.0
    return audio if loudest < 1e-6 else (audio * (peak / loudest)).astype(np.float32)


def resample(audio: np.ndarray, rate_in: int, rate_out: int = SAMPLE_RATE) -> np.ndarray:
    """Resamples with polyphase filtering (scipy), which keeps speech intelligible."""
    if rate_in == rate_out:
        return audio.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    divisor = gcd(rate_in, rate_out)
    return resample_poly(audio, rate_out // divisor, rate_in // divisor).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray) -> None:
    """Writes 16 kHz mono 16-bit PCM WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(audio, -1.0, 1.0), SAMPLE_RATE, subtype="PCM_16")


def read_audio(path: Path) -> np.ndarray:
    """Reads any soundfile-readable file as float32 mono at 16 kHz."""
    audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return resample(audio.mean(axis=1), rate)


def wav_bytes(audio: np.ndarray) -> bytes:
    """Encodes audio as an in-memory 16 kHz mono 16-bit WAV."""
    buffer = io.BytesIO()
    sf.write(buffer, np.clip(audio, -1.0, 1.0), SAMPLE_RATE, subtype="PCM_16", format="WAV")
    return buffer.getvalue()


def rms_dbfs(audio: np.ndarray) -> float:
    """Loudness of a block in dB relative to full scale (-100 for silence)."""
    if audio.size == 0:
        return -100.0
    rms = float(np.sqrt(np.mean(np.square(audio))))
    return -100.0 if rms < 1e-9 else 20.0 * float(np.log10(rms))
