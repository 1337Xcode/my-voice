"""Word error rate: jiwer after Whisper's English normaliser on both sides."""

import json
from functools import lru_cache

import jiwer

# The base model's repo carries normalizer.json, the British-to-American spelling map the normaliser needs.
NORMALIZER_REPO = "openai/whisper-large-v3-turbo"


@lru_cache(maxsize=1)
def english_normalizer():
    """Whisper's EnglishTextNormalizer, built once with the model's spelling map."""
    from huggingface_hub import hf_hub_download
    from transformers.models.whisper.english_normalizer import EnglishTextNormalizer

    with open(hf_hub_download(NORMALIZER_REPO, "normalizer.json"), encoding="utf-8") as handle:
        return EnglishTextNormalizer(json.load(handle))


def normalise(text: str) -> str:
    """Text as WER compares it: lower case, no punctuation, numbers and spellings standardised."""
    return english_normalizer()(text or "").strip()


def wer_percent(references: list[str], hypotheses: list[str]) -> float:
    """Corpus WER in percent over all pairs (total errors over total reference words).

    Pairs whose reference normalises to nothing carry no words to score and are skipped.
    """
    if len(references) != len(hypotheses):
        raise ValueError(f"{len(references)} references but {len(hypotheses)} hypotheses.")
    pairs = [(normalise(ref), normalise(hyp)) for ref, hyp in zip(references, hypotheses)]
    pairs = [(ref, hyp) for ref, hyp in pairs if ref]
    if not pairs:
        raise ValueError("No reference words to score.")
    # An empty hypothesis scores as all deletions.
    output = jiwer.process_words([ref for ref, _ in pairs], [hyp for _, hyp in pairs])
    return round(100.0 * output.wer, 2)


def clip_wer_percent(reference: str, hypothesis: str) -> float:
    """WER in percent for one clip."""
    return wer_percent([reference], [hypothesis])


def words_understood(wer: float) -> float:
    """100 minus WER, clamped to 0..100."""
    return round(min(100.0, max(0.0, 100.0 - wer)), 2)
