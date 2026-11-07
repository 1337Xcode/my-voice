"""Whisper large-v3-turbo with hot-swappable LoRA adapters: n-best decoding with hallucination guards (spec 8.4A)."""

import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

BASE_MODEL = "openai/whisper-large-v3-turbo"
NUM_BEAMS = 5
NBEST = 5
# A hypothesis whose text compresses this well is a repetition loop, not speech (OpenAI's own cut-off).
MAX_COMPRESSION_RATIO = 2.4
# Above this no-speech probability the turn is treated as silence or noise.
MAX_NO_SPEECH_PROBABILITY = 0.6
# Whisper's stock outputs on silence and noise; dropped when a hypothesis is only this.
FILLER_OUTPUTS = {
    "thank you", "thank you for watching", "thanks for watching", "thank you very much for watching",
    "please subscribe", "subscribe", "like and subscribe", "you", "bye", "the end", "amaraorg",
    "subtitles by the amaraorg community", "transcribed by", "so",
}


@dataclass
class Hypothesis:
    """One recogniser guess with its length-normalised log-probability."""

    text: str
    logprob: float


@dataclass
class Recognition:
    """The n-best result for one utterance, with the guards' verdicts and timing."""

    hypotheses: list[Hypothesis]
    no_speech_probability: float
    dropped: list[str]
    ms: float


def compression_ratio(text: str) -> float:
    """Byte length over zlib-compressed length; repetition loops score high."""
    data = text.encode("utf-8")
    return len(data) / max(1, len(zlib.compress(data)))


def filler_key(text: str) -> str:
    """Lower-case letters and spaces only, for comparing against the filler list."""
    return " ".join("".join(ch for ch in text.lower() if ch.isalpha() or ch == " ").split())


def keep_hypothesis(text: str) -> bool:
    """False for empty text, stock filler outputs and repetition loops."""
    key = filler_key(text)
    return bool(key) and key not in FILLER_OUTPUTS and compression_ratio(text) <= MAX_COMPRESSION_RATIO


class Whisper:
    """The loaded base model and processor, the active adapter, and a lock so one decode runs at a time."""

    def __init__(self, model, processor, device: str):
        self.model = model
        self.processor = processor
        self.device = device
        self.lock = threading.Lock()
        self.adapter_path: str | None = None
        self.adapters: dict[str, str] = {}
        self.no_speech_id = processor.tokenizer.convert_tokens_to_ids("<|nospeech|>")
        self.sot_id = processor.tokenizer.convert_tokens_to_ids("<|startoftranscript|>")

    def set_adapter(self, path: str | None) -> None:
        """Activates the LoRA adapter at `path` (loaded once, kept for later swaps), or none for stock."""
        with self.lock:
            self.adapter_path = str(path) if path else None
            if path is None:
                return
            name = self.adapters.get(str(path)) or self._load_adapter(str(path))
            self.model.set_adapter(name)

    def _load_adapter(self, path: str) -> str:
        from peft import PeftModel

        name = f"a{len(self.adapters)}"
        if not self.adapters:
            self.model = PeftModel.from_pretrained(self.model, path, adapter_name=name)
        else:
            self.model.load_adapter(path, adapter_name=name)
        self.model.eval()
        self.adapters[path] = name
        return name

    def nbest(self, audio: np.ndarray, n: int = NBEST, stock: bool = False) -> Recognition:
        """Decodes the 5 best hypotheses (beam 5, temperature 0, English, no timestamps)."""
        with self.lock:
            started = time.perf_counter()
            features = self._features(audio)
            with self._adapter_context(stock):
                no_speech = self._no_speech_probability(features)
                texts, scores = self._beam_search(features, n)
            kept, dropped = [], []
            for text, score in zip(texts, scores):
                (kept if keep_hypothesis(text) else dropped).append((text.strip(), score))
            if no_speech > MAX_NO_SPEECH_PROBABILITY:
                dropped, kept = dropped + kept, []
            hypotheses = [Hypothesis(text, round(score, 4)) for text, score in kept]
            return Recognition(hypotheses, round(no_speech, 4), [t for t, _ in dropped], (time.perf_counter() - started) * 1000)

    def transcribe(self, audio: np.ndarray, stock: bool = False) -> str:
        """The single best text, or "" when the guards drop everything."""
        recognition = self.nbest(audio, n=1, stock=stock)
        return recognition.hypotheses[0].text if recognition.hypotheses else ""

    def greedy(self, audio: np.ndarray) -> str:
        """A fast greedy decode for live partial words (spec 8.10)."""
        import torch

        with self.lock, torch.inference_mode():
            features = self._features(audio)
            ids = self.model.generate(input_features=features, num_beams=1, do_sample=False, language="en", task="transcribe", max_new_tokens=96)
            return self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip()

    def _features(self, audio: np.ndarray):
        import torch

        inputs = self.processor(audio, sampling_rate=16_000, return_tensors="pt")
        return inputs.input_features.to(self.device, dtype=torch.float16)

    def _adapter_context(self, stock: bool):
        from contextlib import nullcontext

        if stock and self.adapters:
            return self.model.disable_adapter()
        return nullcontext()

    def _no_speech_probability(self, features) -> float:
        """The probability of <|nospeech|> right after <|startoftranscript|>, as OpenAI's decoder computes it."""
        import torch

        with torch.inference_mode():
            decoder_ids = torch.tensor([[self.sot_id]], device=self.device)
            logits = self.model(input_features=features, decoder_input_ids=decoder_ids).logits
            return float(torch.softmax(logits[0, -1].float(), dim=-1)[self.no_speech_id])

    def _beam_search(self, features, n: int) -> tuple[list[str], list[float]]:
        import torch

        with torch.inference_mode():
            out = self.model.generate(
                input_features=features, num_beams=max(NUM_BEAMS, n), num_return_sequences=n, length_penalty=1.0,
                do_sample=False, return_dict_in_generate=True, output_scores=True, language="en", task="transcribe",
                max_new_tokens=128,
            )
        texts = self.processor.batch_decode(out.sequences, skip_special_tokens=True)
        scores = out.sequences_scores.float().tolist() if n > 1 or hasattr(out, "sequences_scores") else [0.0] * len(texts)
        return texts, scores


def load_whisper(device: str = "cuda", cache_dir: str | None = None) -> Whisper:
    """Loads the base model in fp16 with SDPA attention, ready for adapters."""
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    processor = WhisperProcessor.from_pretrained(BASE_MODEL, cache_dir=cache_dir)
    model = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL, torch_dtype=torch.float16, attn_implementation="sdpa", cache_dir=cache_dir)
    model.to(device).eval()
    return Whisper(model, processor, device)


def adapter_exists(path: Path) -> bool:
    """True when the folder holds a PEFT adapter."""
    return (path / "adapter_config.json").exists()
