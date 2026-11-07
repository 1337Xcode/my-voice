"""Clip conversion (spec 7.1): edges trimmed to at most 200 ms of silence, peak-normalised, 16 kHz mono 16-bit wav."""

import shutil

import numpy as np
import pytest
import soundfile as sf

from voice.clips.convert import convert_to_clip, prepare_clip, sound_span

RATE = 16_000


def sweep(seconds: float, rate: int = RATE, amplitude: float = 0.3) -> np.ndarray:
    """A 200 Hz to 3 kHz linear sine sweep, speech-band signal for the conversion checks."""
    t = np.arange(int(seconds * rate)) / rate
    phase = 2 * np.pi * (200 * t + (3000 - 200) * t**2 / (2 * seconds))
    return (amplitude * np.sin(phase)).astype(np.float32)


def padded(signal: np.ndarray, before_s: float, after_s: float, rate: int = RATE) -> np.ndarray:
    """The signal with near-silence (a -80 dBFS hiss) before and after."""
    rng = np.random.default_rng(0)
    hiss = lambda seconds: (1e-4 * rng.standard_normal(int(seconds * rate))).astype(np.float32)
    return np.concatenate([hiss(before_s), signal, hiss(after_s)])


def test_long_silences_are_cut_to_200_ms_each_side():
    clip = prepare_clip(padded(sweep(2.0), 1.0, 1.5))
    assert abs(len(clip) / RATE - 2.4) <= 0.02


def test_short_silences_are_kept_whole():
    clip = prepare_clip(padded(sweep(1.0), 0.1, 0.05))
    assert abs(len(clip) / RATE - 1.15) <= 0.01


def test_clip_is_peak_normalised():
    clip = prepare_clip(padded(sweep(1.0, amplitude=0.1), 0.5, 0.5))
    assert np.max(np.abs(clip)) == pytest.approx(0.95, abs=1e-4)


def test_the_sound_span_finds_the_sweep():
    start, end = sound_span(padded(sweep(1.0), 0.5, 0.5))
    assert abs(start / RATE - 0.5) <= 0.01 and abs(end / RATE - 1.5) <= 0.01


def test_pure_silence_is_left_alone():
    silence = np.zeros(RATE, dtype=np.float32)
    assert sound_span(silence) is None
    assert len(prepare_clip(silence)) == RATE


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed on this machine (it is in the Modal image)")
def test_a_44k_stereo_file_becomes_a_16k_mono_16_bit_wav(tmp_path):
    stereo = np.stack([padded(sweep(1.0, 44_100), 0.6, 0.6, 44_100)] * 2, axis=1)
    sf.write(tmp_path / "in.wav", stereo, 44_100)
    duration = convert_to_clip(tmp_path / "in.wav", tmp_path / "out.wav")
    info = sf.info(str(tmp_path / "out.wav"))
    assert (info.samplerate, info.channels, info.subtype) == (16_000, 1, "PCM_16")
    assert abs(duration - 1.4) <= 0.03
