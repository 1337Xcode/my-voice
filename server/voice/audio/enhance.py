"""Speech enhancement front ends tried before recognition (docs/IMPROVEMENTS.md, "Speech enhancement").

`load_enhancer(name, device)` returns an `Enhancer`; `Enhancer.process` takes and returns 16 kHz mono float32 audio of the same length
and records how long it took. Every name in ENHANCER_NAMES is a real implementation; a name whose package is missing raises ImportError.
"""

import os
import sys
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

SAMPLE_RATE = 16_000
# Cut-off of the high-pass: below the lowest voiced pitch, so it only removes rumble, handling noise and mains hum.
HIGHPASS_HZ = 80
HIGHPASS_ORDER = 4
# Integrated loudness the loudness step aims for (EBU R128 broadcast reference).
TARGET_LUFS = -23.0
# BS.1770 integrates over 400 ms blocks, so shorter audio has no loudness to measure.
MIN_LOUDNESS_S = 0.4
# DeepFilterNet works at 48 kHz.
DEEPFILTER_RATE = 48_000
# The "soft" DeepFilterNet variant never removes more than this, to keep weak consonants.
SOFT_ATTENUATION_DB = 12.0
# Where baked-in model files live (the evaluation image downloads them at build time).
MODELS_DIR = Path(os.environ.get("ENHANCER_MODELS_ROOT", "/root/enhancers"))

SPEECHBRAIN_SOURCES = {
    "metricgan_plus": "speechbrain/metricgan-plus-voicebank",
    "sepformer_wham16k": "speechbrain/sepformer-wham16k-enhancement",
}


@dataclass
class Enhancer:
    """A loaded enhancement step: `process` cleans audio and `last_ms` holds the time of the latest call."""

    name: str
    device: str
    run: Callable[[np.ndarray], np.ndarray]
    last_ms: float = field(default=0.0)

    def process(self, audio: np.ndarray) -> np.ndarray:
        """Enhanced audio, float32, the same length as the input and never beyond full scale."""
        started = time.perf_counter()
        enhanced = np.asarray(self.run(np.asarray(audio, dtype=np.float32)), dtype=np.float32)
        if self.device.startswith("cuda"):
            import torch

            torch.cuda.synchronize()
        self.last_ms = (time.perf_counter() - started) * 1000
        return limit_peak(match_length(enhanced, audio.size))


def match_length(audio: np.ndarray, length: int) -> np.ndarray:
    """Trims or zero-pads to exactly `length` samples."""
    return audio[:length] if audio.size >= length else np.pad(audio, (0, length - audio.size))


def limit_peak(audio: np.ndarray, ceiling: float = 0.99) -> np.ndarray:
    """Scales audio down when it would clip; quieter audio is left alone."""
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return audio if peak <= ceiling else (audio * (ceiling / peak)).astype(np.float32)


def highpass(audio: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """Causal Butterworth high-pass (no look-ahead, so it works on a live stream too)."""
    from scipy.signal import sosfilt

    return sosfilt(sos, audio).astype(np.float32)


def normalise_loudness(audio: np.ndarray) -> np.ndarray:
    """Scales audio to TARGET_LUFS (BS.1770), without ever clipping; audio too short or silent is returned unchanged."""
    import pyloudnorm

    if audio.size < MIN_LOUDNESS_S * SAMPLE_RATE or float(np.max(np.abs(audio))) < 1e-4:
        return audio
    loudness = pyloudnorm.Meter(SAMPLE_RATE).integrated_loudness(audio)
    if not np.isfinite(loudness):
        return audio
    gain = 10 ** ((TARGET_LUFS - loudness) / 20)
    return limit_peak((audio * gain).astype(np.float32))


def build_highpass(device: str) -> Callable[[np.ndarray], np.ndarray]:
    """80 Hz high-pass."""
    from scipy.signal import butter

    sos = butter(HIGHPASS_ORDER, HIGHPASS_HZ, btype="highpass", fs=SAMPLE_RATE, output="sos")
    return lambda audio: highpass(audio, sos)


def build_loudnorm(device: str) -> Callable[[np.ndarray], np.ndarray]:
    """Loudness normalisation to -23 LUFS."""
    return normalise_loudness


def build_highpass_loudnorm(device: str) -> Callable[[np.ndarray], np.ndarray]:
    """High-pass, then loudness normalisation."""
    cut = build_highpass(device)
    return lambda audio: normalise_loudness(cut(audio))


def build_noisereduce(device: str, nonstationary: bool) -> Callable[[np.ndarray], np.ndarray]:
    """The noisereduce spectral-gating baseline on the GPU (its torch implementation)."""
    import torch
    from noisereduce.torchgate import TorchGate

    gate = TorchGate(sr=SAMPLE_RATE, nonstationary=nonstationary).to(device)

    def run(audio: np.ndarray) -> np.ndarray:
        with torch.inference_mode():
            return gate(torch.from_numpy(audio)[None].to(device))[0].cpu().numpy()

    return run


def install_torchaudio_shim() -> None:
    """DeepFilterNet 0.5.6 imports `torchaudio.backend.common.AudioMetaData`, which torchaudio removed; this supplies it.

    Only DeepFilterNet's file-loading helpers use it, and this code never loads files through DeepFilterNet.
    """
    if "torchaudio.backend.common" in sys.modules:
        return
    import torchaudio

    backend = types.ModuleType("torchaudio.backend")
    common = types.ModuleType("torchaudio.backend.common")
    common.AudioMetaData = type("AudioMetaData", (), {})
    backend.common = common
    sys.modules.update({"torchaudio.backend": backend, "torchaudio.backend.common": common})
    torchaudio.backend = backend


def build_deepfilternet(device: str, attenuation_limit_db: float | None) -> Callable[[np.ndarray], np.ndarray]:
    """DeepFilterNet 3 (48 kHz, GPU), with an optional cap on how many dB it may remove."""
    import torch
    from scipy.signal import resample_poly

    install_torchaudio_shim()
    from df.enhance import enhance, init_df

    model, state, _ = init_df(post_filter=False, log_level="WARNING")
    factor = DEEPFILTER_RATE // SAMPLE_RATE

    def run(audio: np.ndarray) -> np.ndarray:
        wide = torch.from_numpy(resample_poly(audio, factor, 1).astype(np.float32))[None]
        with torch.inference_mode():
            clean = enhance(model, state, wide, pad=True, atten_lim_db=attenuation_limit_db)
        return resample_poly(clean[0].numpy(), 1, factor)

    return run


def speechbrain_dir(name: str) -> str:
    """Where SpeechBrain keeps one model's files."""
    return str(MODELS_DIR / name)


def build_metricgan_plus(device: str) -> Callable[[np.ndarray], np.ndarray]:
    """SpeechBrain MetricGAN+ (spectral mask trained on VoiceBank-DEMAND)."""
    import torch
    from speechbrain.inference.enhancement import SpectralMaskEnhancement

    source = SPEECHBRAIN_SOURCES["metricgan_plus"]
    model = SpectralMaskEnhancement.from_hparams(source=source, savedir=speechbrain_dir("metricgan_plus"), run_opts={"device": device})

    def run(audio: np.ndarray) -> np.ndarray:
        with torch.inference_mode():
            noisy = torch.from_numpy(audio)[None].to(device)
            return model.enhance_batch(noisy, lengths=torch.ones(1, device=device))[0].cpu().numpy()

    return run


def build_sepformer(device: str) -> Callable[[np.ndarray], np.ndarray]:
    """SpeechBrain SepFormer trained on WHAM! 16 kHz for noisy-speech enhancement."""
    import torch
    from speechbrain.inference.separation import SepformerSeparation

    source = SPEECHBRAIN_SOURCES["sepformer_wham16k"]
    model = SepformerSeparation.from_hparams(source=source, savedir=speechbrain_dir("sepformer_wham16k"), run_opts={"device": device})

    def run(audio: np.ndarray) -> np.ndarray:
        with torch.inference_mode():
            return model.separate_batch(torch.from_numpy(audio)[None].to(device))[0, :, 0].cpu().numpy()

    return run


BUILDERS: dict[str, Callable[[str], Callable[[np.ndarray], np.ndarray]]] = {
    "highpass": build_highpass,
    "loudnorm": build_loudnorm,
    "highpass_loudnorm": build_highpass_loudnorm,
    "noisereduce_stationary": lambda device: build_noisereduce(device, nonstationary=False),
    "noisereduce_nonstationary": lambda device: build_noisereduce(device, nonstationary=True),
    "deepfilternet3": lambda device: build_deepfilternet(device, None),
    "deepfilternet3_soft": lambda device: build_deepfilternet(device, SOFT_ATTENUATION_DB),
    "metricgan_plus": build_metricgan_plus,
    "sepformer_wham16k": build_sepformer,
}
ENHANCER_NAMES = tuple(BUILDERS)


def load_enhancer(name: str, device: str = "cpu") -> Enhancer:
    """Loads one enhancer by name onto `device` ("cpu" or "cuda")."""
    if name not in BUILDERS:
        raise ValueError(f"Unknown enhancer {name!r}; choose one of {', '.join(ENHANCER_NAMES)}.")
    return Enhancer(name=name, device=device, run=BUILDERS[name](device))
