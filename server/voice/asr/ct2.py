"""Whisper large-v3-turbo on CTranslate2: the same n-best, guards and adapter swaps as voice.asr.whisper, several times faster (spec 8.4A).

The public API and its semantics match `voice.asr.whisper.Whisper`. A LoRA adapter is merged into the base model and
converted to CTranslate2 float16 once, cached in `<adapter>/ct2/`. The stock model stays loaded for `stock=True`.
"""

import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from voice.asr.whisper import BASE_MODEL, MAX_NO_SPEECH_PROBABILITY, NBEST, NUM_BEAMS, Hypothesis, Recognition, distinct

# The converted adapter sits next to its PEFT files, so it is made once and found again after a restart.
CT2_FOLDER = "ct2"
# The converted stock model; the serving image converts it at build time with ct2-transformers-converter.
STOCK_FOLDER = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "ct2-whisper-large-v3-turbo"
# English, transcribe, no timestamps: the decoder prompt transformers builds for language="en", task="transcribe".
PROMPT_TOKENS = ["<|startoftranscript|>", "<|en|>", "<|transcribe|>", "<|notimestamps|>"]
# Token budgets of the transformers backend (max_new_tokens), end token included.
BEAM_MAX_NEW_TOKENS = 128
GREEDY_MAX_NEW_TOKENS = 96


def hf_logprob(ct2_score: float, text_tokens: int) -> float:
    """A CT2 beam score as the length-normalised log-probability transformers reports (length_penalty 1).

    Both sum the log-probabilities of the text tokens and the end-of-text token. CT2 divides that sum by the text
    tokens only; transformers divides by the text tokens plus the end token.
    """
    return ct2_score * text_tokens / (text_tokens + 1)


def max_length_for(new_tokens: int) -> int:
    """CT2's `max_length` for a budget of new tokens: Whisper.generate decodes at most max_length // 2 of them."""
    return 2 * new_tokens


def recognition(texts: list[str], scores: list[float], no_speech: float, n: int, started: float) -> Recognition:
    """The guarded n-best result, built exactly as the transformers backend builds it."""
    kept, dropped = distinct(texts, scores, n)
    if no_speech > MAX_NO_SPEECH_PROBABILITY:
        dropped, kept = dropped + [text for text, _, _ in kept], []
    hypotheses = [Hypothesis(text, round(score, 4), support) for text, score, support in kept]
    return Recognition(hypotheses, round(no_speech, 4), dropped, (time.perf_counter() - started) * 1000)


class CT2Whisper:
    """The stock and active CTranslate2 models, the processor for features and text, and a lock so one decode runs at a time."""

    def __init__(self, stock, processor, device: str):
        self.stock = stock
        self.model = stock
        self.processor = processor
        self.device = device
        self.lock = threading.Lock()
        self.adapter_path: str | None = None
        self.last_split_ms: dict[str, int] = {}
        self.prompt = processor.tokenizer.convert_tokens_to_ids(PROMPT_TOKENS)

    def set_adapter(self, path: str | None) -> None:
        """Activates the adapter at `path` (converted on first use, then loaded from `<path>/ct2/`), or none for stock.

        The previous adapter's model is released once the swap is done; the stock model is always kept.
        """
        key = str(path) if path else None
        if key == self.adapter_path:
            return
        model = load_model(prepare_ct2(key), self.device) if key else self.stock
        with self.lock:
            self.adapter_path, self.model = key, model

    def nbest(self, audio: np.ndarray, n: int = NBEST, stock: bool = False, beams: int = NUM_BEAMS) -> Recognition:
        """Decodes the n best distinct hypotheses and the no-speech probability in one beam search (temperature 0)."""
        width = max(beams, n)
        with self.lock:
            started = time.perf_counter()
            features = self._features(audio)
            extracted = time.perf_counter()
            result = (self.stock if stock else self.model).generate(
                features, [self.prompt], beam_size=width, num_hypotheses=width, length_penalty=1.0,
                return_scores=True, return_no_speech_prob=True, max_length=max_length_for(BEAM_MAX_NEW_TOKENS),
            )[0]
            self.last_split_ms = {"features": round((extracted - started) * 1000), "beams": round((time.perf_counter() - extracted) * 1000)}
        texts = self.processor.batch_decode(result.sequences_ids, skip_special_tokens=True)
        scores = [hf_logprob(score, len(ids)) for score, ids in zip(result.scores, result.sequences_ids)]
        return recognition(texts, scores, result.no_speech_prob, n, started)

    def transcribe(self, audio: np.ndarray, stock: bool = False) -> str:
        """The single best text, or "" when the guards drop everything."""
        result = self.nbest(audio, n=1, stock=stock)
        return result.hypotheses[0].text if result.hypotheses else ""

    def greedy(self, audio: np.ndarray) -> str:
        """A fast greedy decode for live partial words (spec 8.10)."""
        with self.lock:
            result = self.model.generate(self._features(audio), [self.prompt], beam_size=1, max_length=max_length_for(GREEDY_MAX_NEW_TOKENS))[0]
        return self.processor.decode(result.sequences_ids[0], skip_special_tokens=True).strip()

    def _features(self, audio: np.ndarray):
        """The log-mel features transformers computes (on the GPU when there is one), as a CTranslate2 array."""
        import ctranslate2

        inputs = self.processor.feature_extractor(audio, sampling_rate=16_000, return_tensors="np", device=self.device)
        return ctranslate2.StorageView.from_array(np.ascontiguousarray(inputs.input_features, dtype=np.float32))


def load_model(folder: Path, device: str):
    """Loads a converted model: float16 on the GPU, the CPU's default type otherwise."""
    import ctranslate2

    return ctranslate2.models.Whisper(str(folder), device=device, compute_type="float16" if device == "cuda" else "default")


def is_converted(folder: Path) -> bool:
    """True when the folder holds a finished CTranslate2 conversion."""
    return (folder / "model.bin").is_file()


def convert(model_path: str, folder: Path) -> None:
    """Converts a transformers Whisper checkpoint to CTranslate2 float16 in `folder`, written whole or not at all."""
    from ctranslate2.converters import TransformersConverter

    staging = folder.with_name(folder.name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    TransformersConverter(model_path, load_as_float16=True).convert(str(staging), quantization="float16", force=True)
    shutil.rmtree(folder, ignore_errors=True)
    staging.rename(folder)


def merge_adapter(adapter_path: str, output: Path) -> None:
    """Folds the LoRA weights into a float32 copy of the base model on the CPU and saves it in float16."""
    import torch
    from peft import PeftModel
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    base = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL, dtype=torch.float32)
    merged = PeftModel.from_pretrained(base, adapter_path).merge_and_unload()
    merged.to(torch.float16).save_pretrained(output)
    WhisperProcessor.from_pretrained(BASE_MODEL).save_pretrained(output)


def prepare_ct2(adapter_path: str) -> Path:
    """Merges the adapter into the base model and converts it to `<adapter>/ct2/` once; returns that folder.

    Call it when a version is trained or registered, so the serving container's first swap only loads it.
    """
    folder = Path(adapter_path) / CT2_FOLDER
    if not is_converted(folder):
        with tempfile.TemporaryDirectory() as merged:
            merge_adapter(adapter_path, Path(merged))
            convert(merged, folder)
    return folder


def prepare_stock_ct2() -> Path:
    """The converted stock model, converting it now if the image did not."""
    if not is_converted(STOCK_FOLDER):
        convert(BASE_MODEL, STOCK_FOLDER)
    return STOCK_FOLDER


def load_ct2_whisper(device: str = "cuda") -> CT2Whisper:
    """Loads the stock model in float16 with the transformers processor, ready for adapters."""
    from transformers import WhisperProcessor

    processor = WhisperProcessor.from_pretrained(BASE_MODEL)
    return CT2Whisper(load_model(prepare_stock_ct2(), device), processor, device)
