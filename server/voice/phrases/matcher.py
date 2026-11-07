"""Phrase matcher: speaker-dependent DTW template matching on WavLM features, no training needed.

A phrase is matched by comparing the utterance's frame features with every saved recording ("template") of every
phrase. A phrase's distance is its closest template. The best distance is accepted only if it is below a threshold
learned from how far apart his own repeats of the same phrase land.
"""

import wave
from dataclasses import dataclass
from time import perf_counter

import numpy as np
import torch

from voice.phrases.bank import MAX_TEMPLATES, load_bank
from voice.phrases.dtw import dtw_batch
from voice.phrases.features import SAMPLE_RATE, Trim, load_wavlm, make_silero_trim, utterance_features
from voice.storage import speaker_dir

__all__ = [
    "PhraseMatch", "MatchResult", "PhraseMatcher", "Calibration", "choose_layer", "load_wavlm", "load_templates",
    "learn_threshold", "rank_phrases", "phrase_min_distances", "pairwise_distances", "loo_report",
]

TOP_K = 3
DEFAULT_LAYER = 6
# Fewer within-phrase pairs than this and the 95th percentile means nothing, so a fixed default is used instead.
MIN_WITHIN_PAIRS = 5
WITHIN_PERCENTILE = 95
# Defaults while the bank has fewer than MIN_WITHIN_PAIRS pairs of repeats. They are conservative: below the
# distances at which unrelated sentences from the first speaker's recordings appear (all 190 pairs >= 0.73 at
# layer 6, measured with server/scripts_phrase_eval.py) and well above the 0.16 that re-cutting one clip adds,
# so an unfamiliar utterance is rejected rather than voiced as a wrong phrase.
DEFAULT_THRESHOLD = 0.55
DEFAULT_TEMPERATURE = 0.03
MIN_TEMPERATURE = 0.01
# Cap on pairs x anti-diagonals x frames per DTW batch; keeps the skewed cost tensor near 100 MB.
_PAIR_BUDGET = 25_000_000


@dataclass
class PhraseMatch:
    """One candidate phrase: its distance (lower is closer), softmax score, and the gap to the next phrase."""

    phrase_id: str
    text: str
    distance: float
    score: float
    margin: float


@dataclass
class MatchResult:
    """Outcome of one match: the top 3 phrases (empty when rejected), the decision data and the time taken."""

    matches: list[PhraseMatch]
    rejected: bool
    best_distance: float | None
    threshold: float
    ms: float
    # "learned" when the threshold comes from his repeats, "default" while there are too few pairs.
    threshold_source: str = "default"


@dataclass(frozen=True)
class Calibration:
    """The reject threshold and softmax temperature, and where they came from."""

    threshold: float
    temperature: float
    source: str
    n_pairs: int


def learn_threshold(within_distances: list[float]) -> Calibration:
    """Threshold = 95th percentile of within-phrase distances; temperature = that percentile minus the median.

    The temperature is the spread of genuine repeats: a rival phrase one spread farther than the best one scores
    1/e as much. With fewer than MIN_WITHIN_PAIRS pairs, returns the documented conservative defaults.
    """
    if len(within_distances) < MIN_WITHIN_PAIRS:
        return Calibration(DEFAULT_THRESHOLD, DEFAULT_TEMPERATURE, "default", len(within_distances))
    top = float(np.percentile(within_distances, WITHIN_PERCENTILE))
    spread = top - float(np.median(within_distances))
    return Calibration(top, max(MIN_TEMPERATURE, spread), "learned", len(within_distances))


def phrase_min_distances(template_distances: np.ndarray, owner: np.ndarray, n_phrases: int) -> np.ndarray:
    """Each phrase's distance is its closest template's; a phrase with no templates gets infinity."""
    best = np.full(n_phrases, np.inf)
    np.minimum.at(best, owner, template_distances)
    return best


def rank_phrases(
    distances: np.ndarray, phrase_ids: list[str], texts: list[str], temperature: float, threshold: float
) -> list[PhraseMatch]:
    """Top 3 phrases by distance with softmax scores over all phrases and the margin to the next phrase.

    The last candidate's margin is measured to the 4th phrase; with no further phrase it is the room left
    under the threshold, so a one-phrase bank still gets a finite margin.
    """
    order = np.argsort(distances, kind="stable")
    finite = np.isfinite(distances)
    if not finite.any():
        return []
    logits = np.where(finite, -distances / temperature, -np.inf)
    weights = np.exp(logits - logits[order[0]])
    scores = weights / weights.sum()
    matches: list[PhraseMatch] = []
    for rank, index in enumerate(order[:TOP_K]):
        if not finite[index]:
            break
        rival = order[rank + 1] if rank + 1 < len(order) and finite[order[rank + 1]] else None
        if rival is not None:
            margin = float(distances[rival] - distances[index])
        else:
            margin = max(threshold - float(distances[index]), 0.0)
        matches.append(PhraseMatch(phrase_ids[index], texts[index], float(distances[index]), float(scores[index]), margin))
    return matches


def pairwise_distances(frames: list[torch.Tensor]) -> np.ndarray:
    """Symmetric [N, N] matrix of DTW distances between all utterances (zero diagonal), computed in batches."""
    count = len(frames)
    matrix = np.zeros((count, count))
    if count < 2:
        return matrix
    lengths = torch.tensor([len(f) for f in frames], device=frames[0].device)
    padded = torch.nn.utils.rnn.pad_sequence(frames, batch_first=True)
    first, second = np.triu_indices(count, k=1)
    longest = padded.shape[1]
    chunk = max(8, _PAIR_BUDGET // (2 * longest * longest))
    for start in range(0, len(first), chunk):
        rows, cols = first[start : start + chunk], second[start : start + chunk]
        i = torch.from_numpy(rows).to(padded.device)
        j = torch.from_numpy(cols).to(padded.device)
        matrix[rows, cols] = dtw_batch(padded[i], lengths[i], padded[j], lengths[j]).cpu().numpy()
    return matrix + matrix.T


def _within_pairs(owner: np.ndarray) -> list[tuple[int, int]]:
    """Index pairs of two different recordings of the same phrase."""
    count = len(owner)
    return [(i, j) for i in range(count) for j in range(i + 1, count) if owner[i] == owner[j]]


def _loo_query(
    matrix: np.ndarray, owner: np.ndarray, pairs: list[tuple[int, int]], query: int, phrase_ids: list[str], texts: list[str]
) -> tuple[list[PhraseMatch], bool]:
    """Matches one template against all the others, using a threshold learned without the query's own pairs."""
    distances = matrix[query].copy()
    distances[query] = np.inf
    phrase_d = phrase_min_distances(distances, owner, len(phrase_ids))
    cal = learn_threshold([float(matrix[i, j]) for i, j in pairs if query not in (i, j)])
    matches = rank_phrases(phrase_d, phrase_ids, texts, cal.temperature, cal.threshold)
    return matches, not matches or matches[0].distance > cal.threshold


def loo_report(matrix: np.ndarray, owner: np.ndarray, phrase_ids: list[str], texts: list[str]) -> dict:
    """Leave-one-out evaluation from a template-by-template distance matrix.

    Each template in turn becomes the query and is removed from the bank (its pairs also leave the threshold).
    Queries whose phrase still has another template are scored: accuracy counts a rejection as wrong. Queries whose
    phrase had only that one template have no right answer, so they only measure the reject rate.
    """
    pairs = _within_pairs(owner)
    per_phrase = {pid: {"n": 0, "correct": 0} for pid in phrase_ids}
    scored = correct = top3 = rejected_scored = orphans = rejected_orphans = 0
    margins: list[float] = []
    for query in range(len(owner)):
        matches, rejected = _loo_query(matrix, owner, pairs, query, phrase_ids, texts)
        if (owner == owner[query]).sum() < 2:
            orphans += 1
            rejected_orphans += rejected
            continue
        truth = phrase_ids[owner[query]]
        hit = not rejected and matches[0].phrase_id == truth
        scored += 1
        rejected_scored += rejected
        correct += hit
        top3 += any(m.phrase_id == truth for m in matches)
        per_phrase[truth]["n"] += 1
        per_phrase[truth]["correct"] += hit
        margins += [matches[0].margin] if matches else []
    return {
        "accuracy": correct / scored if scored else 0.0,
        "n": scored,
        "top3_accuracy": top3 / scored if scored else 0.0,
        "reject_rate": rejected_scored / scored if scored else 0.0,
        "n_orphans": orphans,
        "orphan_reject_rate": rejected_orphans / orphans if orphans else 0.0,
        "mean_margin": float(np.mean(margins)) if margins else 0.0,
        "per_phrase": {pid: {**v, "accuracy": v["correct"] / v["n"]} for pid, v in per_phrase.items() if v["n"]},
    }


class PhraseMatcher:
    """Matches an utterance against his saved phrase recordings."""

    def __init__(self, wavlm_model, feature_extractor, device: str, layer: int = DEFAULT_LAYER, trim: Trim | None = None):
        """`trim` cuts silence from audio; pass the server's loaded VAD trimmer, or None to load Silero here."""
        self._model = wavlm_model
        self._extractor = feature_extractor
        self._device = device
        self.layer = layer
        self._trim = trim
        self._text: dict[str, str] = {}
        self._frames: dict[str, list[torch.Tensor]] = {}
        self._within: dict[str, list[float]] = {}
        self._calibration = learn_threshold([])
        self._stack: tuple[torch.Tensor, torch.Tensor, np.ndarray] | None = None
        self._phrase_ids: list[str] = []

    def _features(self, audio: np.ndarray) -> torch.Tensor:
        """Normalised frames of the configured layer for one utterance."""
        if self._trim is None:
            self._trim = make_silero_trim()
        feats = utterance_features(self._model, self._extractor, self._device, audio, [self.layer], self._trim)
        return feats[self.layer]

    def _refresh_phrase(self, phrase_id: str) -> None:
        """Recomputes one phrase's within-phrase distances after its templates changed."""
        frames = self._frames[phrase_id]
        matrix = pairwise_distances(frames)
        self._within[phrase_id] = [float(matrix[i, j]) for i in range(len(frames)) for j in range(i + 1, len(frames))]

    def _rebuild(self) -> None:
        """Rebuilds the padded template stack and the calibration; called after any template change."""
        self._phrase_ids = [pid for pid in self._frames if self._frames[pid]]
        flat = [f for pid in self._phrase_ids for f in self._frames[pid]]
        owner = np.array([k for k, pid in enumerate(self._phrase_ids) for _ in self._frames[pid]], dtype=np.int64)
        if flat:
            lengths = torch.tensor([len(f) for f in flat], device=self._device)
            self._stack = (torch.nn.utils.rnn.pad_sequence(flat, batch_first=True), lengths, owner)
        else:
            self._stack = None
        self._calibration = learn_threshold([d for pid in self._phrase_ids for d in self._within.get(pid, [])])

    def set_templates(self, templates: dict[str, tuple[str, list[np.ndarray]]]) -> None:
        """Replaces all templates: phrase_id -> (text, audio clips); features are cached, the 5 latest clips kept."""
        self._text, self._frames, self._within = {}, {}, {}
        for phrase_id, (text, clips) in templates.items():
            self._text[phrase_id] = text
            self._frames[phrase_id] = [self._features(clip) for clip in clips[-MAX_TEMPLATES:]]
            self._refresh_phrase(phrase_id)
        self._rebuild()

    def add_template(self, phrase_id: str, text: str, audio: np.ndarray) -> None:
        """Adds one recording to a phrase (creating it if new), keeping its 5 most recent."""
        self._text[phrase_id] = text
        self._frames[phrase_id] = (self._frames.get(phrase_id, []) + [self._features(audio)])[-MAX_TEMPLATES:]
        self._refresh_phrase(phrase_id)
        self._rebuild()

    @property
    def has_templates(self) -> bool:
        """True once at least one phrase has a recording to match against."""
        return bool(self._phrase_ids)

    def calibration(self) -> Calibration:
        """The current threshold, temperature and whether they are learned or default."""
        return self._calibration

    def match(self, audio: np.ndarray) -> MatchResult:
        """Finds the saved phrases closest to the utterance, or rejects when none is close enough."""
        started = perf_counter()
        cal = self._calibration
        if self._stack is None:
            return MatchResult([], True, None, cal.threshold, (perf_counter() - started) * 1000, cal.source)
        query = self._features(audio)
        refs, lengths, owner = self._stack
        count = refs.shape[0]
        a_len = torch.full((count,), len(query), device=self._device)
        template_d = dtw_batch(query[None].expand(count, -1, -1), a_len, refs, lengths).cpu().numpy()
        phrase_d = phrase_min_distances(template_d, owner, len(self._phrase_ids))
        texts = [self._text[p] for p in self._phrase_ids]
        ranked = rank_phrases(phrase_d, self._phrase_ids, texts, cal.temperature, cal.threshold)
        rejected = ranked[0].distance > cal.threshold
        ms = (perf_counter() - started) * 1000
        return MatchResult([] if rejected else ranked, rejected, ranked[0].distance, cal.threshold, ms, cal.source)

    def leave_one_out(self) -> dict:
        """Accuracy and reject rate when each saved recording is used as the query against the rest."""
        if self._stack is None:
            return {"accuracy": 0.0, "n": 0, "per_phrase": {}, "reject_rate": 0.0}
        flat = [f for pid in self._phrase_ids for f in self._frames[pid]]
        texts = [self._text[p] for p in self._phrase_ids]
        return loo_report(pairwise_distances(flat), self._stack[2], self._phrase_ids, texts)


def choose_layer(
    model, extractor, device: str, templates: dict[str, tuple[str, list[np.ndarray]]],
    layers=range(3, 10), trim: Trim | None = None,
) -> tuple[int, dict]:
    """Picks the WavLM layer with the best leave-one-out accuracy on his clips; returns (layer, report per layer).

    Ties go to the larger mean margin, then to the layer nearest the default. With no phrase that has two
    recordings there is nothing to score, so the default layer is returned with an empty report.
    """
    layers = list(layers)
    if not any(len(clips) > 1 for _, clips in templates.values()):
        return DEFAULT_LAYER, {}
    trim = trim or make_silero_trim()
    phrase_ids = list(templates)
    texts = [templates[p][0] for p in phrase_ids]
    clips = [(k, clip) for k, p in enumerate(phrase_ids) for clip in templates[p][1][-MAX_TEMPLATES:]]
    owner = np.array([k for k, _ in clips], dtype=np.int64)
    per_clip = [utterance_features(model, extractor, device, clip, layers, trim) for _, clip in clips]
    reports = {
        layer: loo_report(pairwise_distances([c[layer] for c in per_clip]), owner, phrase_ids, texts) for layer in layers
    }
    best = max(layers, key=lambda k: (reports[k]["accuracy"], reports[k]["mean_margin"], -abs(k - DEFAULT_LAYER)))
    return best, reports


def _read_clip(path) -> np.ndarray:
    """Reads a 16 kHz mono 16-bit PCM wav (the stored clip format) as float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != SAMPLE_RATE or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(f"{path} is not 16 kHz mono 16-bit PCM.")
        raw = wav.readframes(wav.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def load_templates(speaker: str) -> dict[str, tuple[str, list[np.ndarray]]]:
    """Reads his bank and the template wavs: phrase_id -> (text, [audio]); phrases with no recording are left out."""
    audio_dir = speaker_dir(speaker) / "audio"
    templates: dict[str, tuple[str, list[np.ndarray]]] = {}
    for phrase in load_bank(speaker):
        if phrase.template_clip_ids:
            clips = [_read_clip(audio_dir / f"{clip_id}.wav") for clip_id in phrase.template_clip_ids]
            templates[phrase.id] = (phrase.text, clips)
    return templates
