"""Correction memory: what the recogniser heard, what he meant, and how often."""

import time
import uuid
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from voice.gate.candidates import MemoryHit, normalise
from voice.storage import append_jsonl, latest_by_id, speaker_dir

SOURCES = ("pick", "typed", "review", "spoken")
# Explicit corrections: he chose or typed the sentence, or approved it in Review.
EXPLICIT_SOURCES = ("pick", "typed", "review")
LOOKUP_SIZE = 5
# A stored sentence becomes a candidate once he has confirmed it this many times.
MIN_CONFIRMATIONS = 2
# Normalised character similarity a stored 'heard' must reach to vouch for its 'meant' sentence.
# 0.6 means at most 4 edits in 10 characters: close enough that the same misrecognition recurred,
# loose enough to survive his sentence coming out a little differently each time.
MIN_SIMILARITY = 0.6
# Two 'heard' strings this close (with the same 'meant') count as the same pair recurring.
SAME_PAIR_SIMILARITY = 0.85


def memory_path(speaker: str) -> Path:
    """The speaker's correction memory file."""
    return speaker_dir(speaker) / "memory.jsonl"


def similarity(a: str, b: str) -> float:
    """1 minus the character edit distance over the longer length, after normalising both texts."""
    return Levenshtein.normalized_similarity(normalise(a), normalise(b))


def load_pairs(speaker: str) -> list[dict]:
    """Every stored pair at its latest count, oldest first."""
    return sorted(latest_by_id(memory_path(speaker)).values(), key=lambda pair: pair["created_at"])


def add_pair(speaker: str, heard: str, nbest: list[str], meant: str, source: str) -> dict:
    """Stores a confirmed (heard, meant) pair, or increments the count of the same pair seen before."""
    if source not in SOURCES:
        raise ValueError(f"Unknown memory source {source!r}; expected one of {', '.join(SOURCES)}.")
    if not normalise(meant):
        raise ValueError("A memory pair needs a non-empty meant sentence.")
    for pair in load_pairs(speaker):
        if normalise(pair["meant"]) == normalise(meant) and similarity(pair["heard"], heard) >= SAME_PAIR_SIMILARITY:
            updated = {**pair, "count": pair["count"] + 1, "updated_at": time.time()}
            append_jsonl(memory_path(speaker), updated)
            return updated
    now = time.time()
    record = {"id": uuid.uuid4().hex[:12], "heard": heard, "nbest": nbest[:5], "meant": meant.strip(),
              "source": source, "created_at": now, "updated_at": now, "count": 1}
    append_jsonl(memory_path(speaker), record)
    return record


def similar_pairs(speaker: str, heard: str, size: int = LOOKUP_SIZE) -> list[tuple[dict, float]]:
    """The stored pairs whose 'heard' is most similar to this one, most similar first."""
    scored = [(pair, similarity(pair["heard"], heard)) for pair in load_pairs(speaker)]
    return sorted(scored, key=lambda item: item[1], reverse=True)[:size]


def confirmations(pairs: list[dict]) -> dict[str, int]:
    """How many times each meant sentence (normalised) was confirmed, across all pairs."""
    totals: dict[str, int] = {}
    for pair in pairs:
        key = normalise(pair["meant"])
        totals[key] = totals.get(key, 0) + pair["count"]
    return totals


def lookup(speaker: str, heard_top1: str) -> list[MemoryHit]:
    """Memory candidates for this turn: confirmed 2+ times and heard similarly to now."""
    if not normalise(heard_top1):
        return []
    totals = confirmations(load_pairs(speaker))
    hits: dict[str, MemoryHit] = {}
    for pair, score in similar_pairs(speaker, heard_top1):
        key = normalise(pair["meant"])
        if score >= MIN_SIMILARITY and totals[key] >= MIN_CONFIRMATIONS and key not in hits:
            hits[key] = MemoryHit(meant=pair["meant"], similarity=round(score, 3), count=totals[key])
    return list(hits.values())
