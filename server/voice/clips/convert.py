"""Turns any recording into the stored clip format: 16 kHz mono 16-bit wav, peak-normalised, edges trimmed."""

import subprocess
from pathlib import Path

import numpy as np

from voice.audio.pcm import EDGE_SILENCE_S, SAMPLE_RATE, peak_normalise, write_wav

FRAME_S = 0.01
# A 10 ms frame counts as sound when it is within 40 dB of the clip's loudest frame (and above -60 dBFS).
SOUND_BELOW_LOUDEST_DB = 40.0
SOUND_FLOOR_DBFS = -60.0
FFMPEG_TIMEOUT_S = 120


def decode_audio(path: Path) -> np.ndarray:
    """Decodes any audio file ffmpeg reads (m4a, wav, flac, mp3, ...) to float32 mono at 16 kHz."""
    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    result = subprocess.run(command, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    if result.returncode != 0:
        raise ValueError(f"Could not decode {path.name}: {result.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(result.stdout, dtype="<f4").copy()


def sound_span(audio: np.ndarray) -> tuple[int, int] | None:
    """First and last sample (exclusive) of the frames that hold sound, or None for a silent clip."""
    frame = int(FRAME_S * SAMPLE_RATE)
    count = len(audio) // frame
    if count == 0:
        return None
    frames = audio[: count * frame].reshape(count, frame)
    level_db = 20.0 * np.log10(np.sqrt(np.mean(frames**2, axis=1)) + 1e-10)
    threshold = max(float(level_db.max()) - SOUND_BELOW_LOUDEST_DB, SOUND_FLOOR_DBFS)
    loud = np.flatnonzero(level_db > threshold)
    if loud.size == 0:
        return None
    return int(loud[0] * frame), int((loud[-1] + 1) * frame)


def trim_edges(audio: np.ndarray) -> np.ndarray:
    """Cuts leading and trailing silence down to at most EDGE_SILENCE_S on each side."""
    span = sound_span(audio)
    if span is None:
        return audio
    keep = int(EDGE_SILENCE_S * SAMPLE_RATE)
    return audio[max(0, span[0] - keep) : min(len(audio), span[1] + keep)]


def prepare_clip(audio: np.ndarray) -> np.ndarray:
    """16 kHz float audio as stored: edges trimmed, then peak-normalised."""
    return peak_normalise(trim_edges(audio.astype(np.float32)))


def convert_to_clip(source: Path, destination: Path) -> float:
    """Converts a recording to the stored wav format and returns its duration in seconds."""
    audio = prepare_clip(decode_audio(source))
    if audio.size == 0:
        raise ValueError(f"{source.name} holds no audio.")
    write_wav(destination, audio)
    return round(len(audio) / SAMPLE_RATE, 3)
