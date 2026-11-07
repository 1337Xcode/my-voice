"""G.711 μ-law, the phone line's audio: decoding, encoding, 8 → 16 kHz conversion and the waiting pulse.

`audioop` is gone from Python 3.13, so the codec is done here with numpy (decoding is a 256-entry lookup table).
"""

import numpy as np

PHONE_RATE = 8_000
# G.711 adds this bias before finding the segment, and clips magnitudes so the biased value fits 15 bits.
BIAS = 0x84
CLIP = 32_635
# Low-pass for the 2× upsampler: passes the phone band (to 3.4 kHz), removes the mirror image above 4 kHz.
UPSAMPLE_TAPS = 63
UPSAMPLE_CUTOFF_HZ = 3_800


def _decode_table() -> np.ndarray:
    """The linear 16-bit value of every μ-law byte (codes are stored bit-inverted)."""
    codes = ~np.arange(256, dtype=np.int32) & 0xFF
    exponent = (codes >> 4) & 0x07
    mantissa = codes & 0x0F
    magnitude = (((mantissa << 3) + BIAS) << exponent) - BIAS
    return np.where(codes & 0x80, -magnitude, magnitude).astype(np.int16)


DECODE_TABLE = _decode_table()


def decode(data: bytes) -> np.ndarray:
    """μ-law bytes to 16-bit linear samples."""
    return DECODE_TABLE[np.frombuffer(data, dtype=np.uint8)]


def encode(samples: np.ndarray) -> bytes:
    """16-bit linear samples to μ-law bytes."""
    linear = samples.astype(np.int32)
    sign = (linear < 0).astype(np.int32) << 7
    magnitude = np.minimum(np.abs(linear), CLIP) + BIAS
    # The segment (exponent) is the position of the highest set bit above bit 7.
    exponent = np.clip(np.floor(np.log2(magnitude)).astype(np.int32) - 7, 0, 7)
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return ((~(sign | (exponent << 4) | mantissa)) & 0xFF).astype(np.uint8).tobytes()


class PhoneAudioDecoder:
    """Turns a call's μ-law 8 kHz chunks into 16 kHz float audio, keeping the filter state across chunks."""

    def __init__(self):
        from scipy.signal import firwin

        # ×2 restores the level that inserting a zero between samples halves.
        self.taps = firwin(UPSAMPLE_TAPS, UPSAMPLE_CUTOFF_HZ, fs=PHONE_RATE * 2) * 2
        self.state = np.zeros(UPSAMPLE_TAPS - 1)

    def decode(self, payload: bytes) -> np.ndarray:
        """One chunk of μ-law bytes to float32 samples at 16 kHz in [-1, 1]."""
        from scipy.signal import lfilter

        narrow = decode(payload).astype(np.float64) / 32768.0
        stuffed = np.zeros(narrow.size * 2)
        stuffed[::2] = narrow
        wide, self.state = lfilter(self.taps, 1.0, stuffed, zi=self.state)
        return wide.astype(np.float32)


def pulse_tone(frequency_hz: float = 440.0, length_ms: int = 120, level: float = 0.06) -> bytes:
    """A short, quiet μ-law beep that tells the callee he is still working on his sentence."""
    t = np.arange(PHONE_RATE * length_ms // 1000) / PHONE_RATE
    # A half-sine envelope fades the beep in and out so it does not click.
    envelope = np.sin(np.pi * t / t[-1])
    return encode(level * 32767 * envelope * np.sin(2 * np.pi * frequency_hz * t))
