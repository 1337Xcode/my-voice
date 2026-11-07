"""Merges recogniser hypotheses, phrase matches, memory and repairs into one de-duplicated candidate set (spec 8.5)."""

import re
from dataclasses import dataclass, field

MAX_CANDIDATES = 10
# When the same sentence comes from several sources, the display text comes from the most trusted one:
# bank phrases and confirmed memory are already punctuated the way he wants them spoken.
SOURCE_ORDER = ("phrase", "memory", "repair", "asr")


@dataclass(frozen=True)
class Hypothesis:
    """One recogniser hypothesis with its length-normalised log-probability."""

    text: str
    logprob: float


@dataclass(frozen=True)
class PhraseMatch:
    """One phrase-bank match from the template matcher (spec 8.4B)."""

    phrase_id: str
    text: str
    distance: float
    score: float
    margin: float


@dataclass(frozen=True)
class MemoryHit:
    """A confirmed sentence from correction memory whose recorded 'heard' resembles this turn."""

    meant: str
    similarity: float
    count: int


@dataclass
class Candidate:
    """One sentence he may have said, with every source and score that supports it."""

    id: str
    text: str
    sources: list[str] = field(default_factory=list)
    asr_rank: int | None = None
    asr_logprob: float | None = None
    phrase_id: str | None = None
    phrase_score: float | None = None
    phrase_margin: float | None = None
    memory_similarity: float | None = None
    memory_count: int | None = None

    @property
    def agree(self) -> int:
        """How many different sources produced this sentence."""
        return len(self.sources)


def normalise(text: str) -> str:
    """Whisper-style normal form for comparing sentences: lower case, no brackets, punctuation or extra spaces."""
    text = text.lower().replace("’", "'")
    text = re.sub(r"[\[(<][^\])>]*[\])>]", " ", text)  # drop bracketed asides like "[music]"
    text = text.replace("'", "")  # "I'd" and "Id" compare equal
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _add(pool: dict[str, Candidate], text: str, source: str) -> Candidate | None:
    """Finds or creates the pooled candidate for this text and records the source; None for empty text."""
    key = normalise(text)
    if not key:
        return None
    candidate = pool.setdefault(key, Candidate(id="", text=text.strip()))
    if source in candidate.sources:
        return candidate
    if candidate.sources and SOURCE_ORDER.index(source) < min(SOURCE_ORDER.index(s) for s in candidate.sources):
        candidate.text = text.strip()
    candidate.sources.append(source)
    return candidate


def _priority(candidate: Candidate) -> tuple:
    """Sort key: more agreeing sources first, then the most trusted source, then recogniser rank."""
    best_source = min(SOURCE_ORDER.index(s) for s in candidate.sources)
    return (-candidate.agree, best_source, candidate.asr_rank or 99)


def build_candidates(
    nbest: list[Hypothesis],
    phrases: list[PhraseMatch],
    memory: list[MemoryHit],
    repairs: list[str] = (),
) -> list[Candidate]:
    """Merges every source into at most 10 candidates with ids c1, c2, ... in priority order."""
    pool: dict[str, Candidate] = {}
    for rank, hypothesis in enumerate(nbest, start=1):
        candidate = _add(pool, hypothesis.text, "asr")
        if candidate and candidate.asr_rank is None:
            candidate.asr_rank, candidate.asr_logprob = rank, hypothesis.logprob
    for match in phrases:
        candidate = _add(pool, match.text, "phrase")
        if candidate and (candidate.phrase_score is None or match.score > candidate.phrase_score):
            candidate.phrase_id, candidate.phrase_score, candidate.phrase_margin = match.phrase_id, match.score, match.margin
    for hit in memory:
        candidate = _add(pool, hit.meant, "memory")
        if candidate and (candidate.memory_similarity is None or hit.similarity > candidate.memory_similarity):
            candidate.memory_similarity, candidate.memory_count = hit.similarity, hit.count
    for sentence in repairs:
        _add(pool, sentence, "repair")
    ranked = sorted(pool.values(), key=_priority)[:MAX_CANDIDATES]
    for index, candidate in enumerate(ranked, start=1):
        candidate.id = f"c{index}"
    return ranked


def describe(candidate: Candidate) -> str:
    """The candidate's evidence in one plain sentence, for the decision model."""
    parts = []
    if candidate.asr_rank is not None:
        parts.append(f"recogniser hypothesis rank {candidate.asr_rank} (log-probability {candidate.asr_logprob:.2f})")
    if candidate.phrase_score is not None:
        parts.append(f"matches his saved phrase by sound (score {candidate.phrase_score:.2f}, margin {candidate.phrase_margin:.2f})")
    if candidate.memory_similarity is not None:
        parts.append(f"he confirmed this sentence {candidate.memory_count} times when the recogniser heard something "
                     f"similar (similarity {candidate.memory_similarity:.2f})")
    if "repair" in candidate.sources:
        parts.append("proposed by the error-correction model from the hypotheses")
    parts.append(f"{candidate.agree} source{'s' if candidate.agree != 1 else ''} agree")
    return "; ".join(parts) + "."


def features(candidate: Candidate) -> dict:
    """The candidate's scores as a plain dict, for JSON state and logs."""
    return {
        "sentence": candidate.text, "sources": candidate.sources, "agree": candidate.agree,
        "asr_rank": candidate.asr_rank, "asr_logprob": candidate.asr_logprob,
        "phrase_score": candidate.phrase_score, "phrase_margin": candidate.phrase_margin,
        "memory_similarity": candidate.memory_similarity, "memory_count": candidate.memory_count,
    }
