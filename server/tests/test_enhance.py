"""Enhancers on real synthetic signals: rumble is removed, a tone in noise gets cleaner, loudness lands on target, lengths are kept."""

import numpy as np
import pytest

from voice.audio.enhance import SAMPLE_RATE, TARGET_LUFS, limit_peak, load_enhancer, match_length

SECONDS = 4


def tone(hz: float, amplitude: float = 0.1) -> np.ndarray:
    """A pure sine, SECONDS long."""
    return (amplitude * np.sin(2 * np.pi * hz * np.arange(SECONDS * SAMPLE_RATE) / SAMPLE_RATE)).astype(np.float32)


def power_db(audio: np.ndarray) -> float:
    """Mean power in dB (full-scale sine = -3 dB)."""
    return float(10 * np.log10(np.mean(audio**2) + 1e-20))


def snr_db(clean: np.ndarray, estimate: np.ndarray) -> float:
    """How far `estimate` is below `clean` as noise: power of clean over power of the difference, in dB."""
    return power_db(clean) - power_db(estimate - clean)


def band_power_db(audio: np.ndarray, low_hz: float, high_hz: float) -> float:
    """Power of the part of `audio` between two frequencies, in dB, read off its spectrum."""
    spectrum = np.abs(np.fft.rfft(audio)) ** 2
    hertz = np.fft.rfftfreq(audio.size, 1 / SAMPLE_RATE)
    return float(10 * np.log10(spectrum[(hertz >= low_hz) & (hertz <= high_hz)].sum() + 1e-20))


def test_highpass_removes_rumble_and_keeps_speech_band():
    mixed = tone(20, 0.2) + tone(1000, 0.1)
    cleaned = load_enhancer("highpass").process(mixed)
    assert band_power_db(mixed, 0, 40) - band_power_db(cleaned, 0, 40) > 30
    assert abs(band_power_db(mixed, 900, 1100) - band_power_db(cleaned, 900, 1100)) < 0.5


def test_loudnorm_lands_on_target_loudness():
    import pyloudnorm

    quiet = tone(440, 0.01) + 0.002 * np.random.default_rng(0).standard_normal(SECONDS * SAMPLE_RATE).astype(np.float32)
    loudness = pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(load_enhancer("loudnorm").process(quiet))
    assert loudness == pytest.approx(TARGET_LUFS, abs=0.5)


def test_loudnorm_leaves_silence_and_clips_too_short_to_measure_alone():
    enhancer = load_enhancer("loudnorm")
    assert np.all(enhancer.process(np.zeros(SAMPLE_RATE, dtype=np.float32)) == 0)
    short = tone(440, 0.01)[: SAMPLE_RATE // 4]
    assert np.array_equal(enhancer.process(short), short)


def test_noise_gate_improves_snr_of_a_tone_in_white_noise():
    pytest.importorskip("noisereduce")
    clean = tone(1000, 0.1)
    noisy = clean + 0.1 * np.random.default_rng(1).standard_normal(clean.size).astype(np.float32)
    enhancer = load_enhancer("noisereduce_stationary")
    cleaned = enhancer.process(noisy)
    assert snr_db(clean, cleaned) > snr_db(clean, noisy) + 3
    assert enhancer.last_ms > 0


def test_every_enhancer_keeps_the_length_and_never_clips():
    loud = tone(300, 1.5)
    out = load_enhancer("highpass_loudnorm").process(loud)
    assert out.shape == loud.shape and out.dtype == np.float32 and float(np.max(np.abs(out))) <= 0.99


def test_unknown_enhancer_names_the_choices():
    with pytest.raises(ValueError, match="deepfilternet3"):
        load_enhancer("krisp")


def test_match_length_trims_and_pads():
    assert match_length(np.ones(10, dtype=np.float32), 6).size == 6
    assert match_length(np.ones(4, dtype=np.float32), 6).tolist() == [1, 1, 1, 1, 0, 0]


def test_limit_peak_only_scales_down():
    assert limit_peak(np.array([2.0, -1.0], dtype=np.float32)).tolist() == pytest.approx([0.99, -0.495])
    assert limit_peak(np.array([0.5], dtype=np.float32)).tolist() == [0.5]
