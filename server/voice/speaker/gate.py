"""The speaker gate for hands-free mode (spec 8.3): is this segment him, or someone else nearby?

Uses WavLM base+ speaker-verification x-vectors (see DECISIONS: SpeechBrain ECAPA needs a torchaudio that doesn't
support our torch). His enrolment centroid comes from 10+ of his clips; the threshold rejects at most 1% of his own.
"""

import threading
import time
from dataclasses import dataclass

import numpy as np

from voice.audio.pcm import read_audio
from voice.clips.records import audio_path, load_clips
from voice.storage import read_json, speaker_dir, write_json

SV_MODEL = "microsoft/wavlm-base-plus-sv"
MIN_ENROLMENT_CLIPS = 10
# At most this share of his own segments may be rejected as "someone else" (spec 8.3).
MAX_SELF_REJECTION = 0.01
MAX_ENROLMENT_CLIPS = 60


@dataclass
class Enrolment:
    """His centroid and the cosine threshold below which a segment is someone else."""

    centroid: np.ndarray
    threshold: float
    clips: int
    self_scores: list[float]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def threshold_from_self_scores(scores: list[float]) -> float:
    """The cosine score that rejects at most 1% of his own clips (the 1st percentile, a little below it)."""
    return float(np.quantile(np.asarray(scores), MAX_SELF_REJECTION)) - 0.01


class SpeakerGate:
    """Embeds segments and compares them with his enrolment."""

    def __init__(self, device: str):
        from transformers import AutoFeatureExtractor, WavLMForXVector

        self.extractor = AutoFeatureExtractor.from_pretrained(SV_MODEL)
        self.model = WavLMForXVector.from_pretrained(SV_MODEL).to(device).eval()
        self.device = device
        self.lock = threading.Lock()
        self.enrolments: dict[str, Enrolment] = {}

    def embed(self, audio: np.ndarray) -> np.ndarray:
        """One x-vector for a 16 kHz segment."""
        import torch

        with self.lock, torch.inference_mode():
            inputs = self.extractor(audio, sampling_rate=16_000, return_tensors="pt").to(self.device)
            return self.model(**inputs).embeddings[0].float().cpu().numpy()

    def enrol(self, speaker: str) -> Enrolment | None:
        """Builds his centroid from his clips (leave-one-out scores pick the threshold); None with too few clips."""
        clips = [c for c in load_clips(speaker).values() if c.ok and not c.excluded and audio_path(speaker, c.id).exists()][:MAX_ENROLMENT_CLIPS]
        if len(clips) < MIN_ENROLMENT_CLIPS:
            return None
        vectors = np.stack([self.embed(read_audio(audio_path(speaker, c.id))) for c in clips])
        total = vectors.sum(axis=0)
        self_scores = [cosine(vectors[i], (total - vectors[i]) / (len(vectors) - 1)) for i in range(len(vectors))]
        enrolment = Enrolment(vectors.mean(axis=0), threshold_from_self_scores(self_scores), len(clips), self_scores)
        write_json(speaker_dir(speaker) / "speaker_gate.json", {"threshold": enrolment.threshold, "clips": enrolment.clips,
                                                                  "self_scores": [round(s, 4) for s in self_scores], "built_at": time.time()})
        self.enrolments[speaker] = enrolment
        return enrolment

    def is_him(self, speaker: str, audio: np.ndarray) -> tuple[bool, float | None]:
        """(True, score) when the segment is his; with no enrolment yet everything counts as his (and score is None)."""
        enrolment = self.enrolments.get(speaker) or self.enrol(speaker)
        if enrolment is None:
            return True, None
        score = cosine(self.embed(audio), enrolment.centroid)
        return score >= enrolment.threshold, round(score, 4)

    def stored_report(self, speaker: str) -> dict:
        return read_json(speaker_dir(speaker) / "speaker_gate.json", {})
