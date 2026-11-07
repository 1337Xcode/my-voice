"""WavLM frame features for the phrase matcher: silence trimming, hidden-state extraction and normalisation."""

from typing import Callable, Iterable

import numpy as np
import torch

SAMPLE_RATE = 16_000
WAVLM_ID = "microsoft/wavlm-base-plus"
# The convolutional front end needs a few hundred samples to produce any frame; 0.1 s keeps very short words alive.
MIN_SAMPLES = SAMPLE_RATE // 10
# A VAD result shorter than this is treated as a misfire and the audio is left untrimmed.
MIN_TRIMMED_SAMPLES = SAMPLE_RATE * 15 // 100

# Silero's default threshold (0.5) drops the quiet tail of his sentences and the cut point flips with a little
# padding (measured: one clip lost 1.9 s). 0.3 keeps the tail; self-distance of a clip re-cut after added
# silence fell from up to 0.62 to up to 0.16.
VAD_THRESHOLD = 0.3
VAD_MIN_SPEECH_MS = 100

Trim = Callable[[np.ndarray], np.ndarray]


def load_wavlm(device: str):
    """Loads WavLM base+ and its feature extractor; returns (model, feature_extractor), model in eval mode on device."""
    from transformers import AutoFeatureExtractor, WavLMModel

    model = WavLMModel.from_pretrained(WAVLM_ID).to(device).eval()
    return model, AutoFeatureExtractor.from_pretrained(WAVLM_ID)


def make_silero_trim() -> Trim:
    """Returns a function that cuts leading and trailing silence using Silero VAD (loaded once, 16 kHz)."""
    from silero_vad import get_speech_timestamps, load_silero_vad

    vad = load_silero_vad()

    def trim(audio: np.ndarray) -> np.ndarray:
        spans = get_speech_timestamps(
            torch.from_numpy(audio), vad, sampling_rate=SAMPLE_RATE, return_seconds=False,
            threshold=VAD_THRESHOLD, min_speech_duration_ms=VAD_MIN_SPEECH_MS,
        )
        if not spans:
            return audio
        cut = audio[spans[0]["start"] : spans[-1]["end"]]
        return cut if len(cut) >= MIN_TRIMMED_SAMPLES else audio

    return trim


def prepare_audio(audio: np.ndarray, trim: Trim) -> np.ndarray:
    """Trims silence, pads to the minimum length and peak-normalises, as the stored clips are."""
    audio = np.ascontiguousarray(audio, dtype=np.float32).reshape(-1)
    audio = trim(audio)
    if len(audio) < MIN_SAMPLES:
        audio = np.pad(audio, (0, MIN_SAMPLES - len(audio)))
    peak = float(np.abs(audio).max())
    return audio / peak * 0.95 if peak > 1e-6 else audio


def normalise_frames(frames: torch.Tensor) -> torch.Tensor:
    """Standardises each feature dimension over the utterance, then scales every frame to unit length.

    After this, one minus a dot product of two frames is their cosine distance.
    """
    centred = frames - frames.mean(dim=0, keepdim=True)
    scaled = centred / (frames.std(dim=0, keepdim=True, unbiased=False) + 1e-5)
    return scaled / (scaled.norm(dim=1, keepdim=True) + 1e-8)


@torch.inference_mode()
def utterance_features(
    model, extractor, device: str, audio: np.ndarray, layers: Iterable[int], trim: Trim
) -> dict[int, torch.Tensor]:
    """Runs WavLM once and returns the normalised frames [T, 768] of each requested hidden layer.

    Layer k is `hidden_states[k]`: 0 is the CNN/projection output, 1 to 12 are the transformer layers.
    """
    prepared = prepare_audio(audio, trim)
    inputs = extractor(prepared, sampling_rate=SAMPLE_RATE, return_tensors="pt")
    hidden = model(inputs.input_values.to(device), output_hidden_states=True).hidden_states
    return {layer: normalise_frames(hidden[layer][0]) for layer in layers}
