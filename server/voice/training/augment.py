"""On-the-fly training augmentation: speed 0.9/1.0/1.1 and, half the time, babble at 0 to 15 dB SNR."""

import numpy as np

from voice.training.babble import babble_segment, mix_at_snr

SPEEDS = (0.9, 1.0, 1.1)
BABBLE_PROBABILITY = 0.5
SNR_RANGE_DB = (0.0, 15.0)


def change_speed(audio: np.ndarray, factor: float) -> np.ndarray:
    """Plays audio `factor` times faster (tempo and pitch together, like tape), by linear resampling."""
    if factor == 1.0 or audio.size < 2:
        return audio
    length = max(2, int(round(len(audio) / factor)))
    return np.interp(np.linspace(0, len(audio) - 1, length), np.arange(len(audio)), audio).astype(np.float32)


def augment(audio: np.ndarray, bank: list[np.ndarray], rng: np.random.Generator) -> np.ndarray:
    """One random augmentation of a training clip (SpecAugment is applied later, inside the model)."""
    audio = change_speed(audio, float(rng.choice(SPEEDS)))
    if bank and rng.random() < BABBLE_PROBABILITY:
        audio = mix_at_snr(audio, babble_segment(bank, len(audio), rng), float(rng.uniform(*SNR_RANGE_DB)))
    return audio
