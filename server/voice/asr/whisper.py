"""Whisper large-v3-turbo with hot-swappable LoRA adapters: n-best decoding with hallucination guards (spec 8.4A)."""

import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

BASE_MODEL = "openai/whisper-large-v3-turbo"
# Beams searched (spec 8.4A). Beams that differ only in case or punctuation are merged and counted as support.
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
    # How many search beams ended on this sentence (case and punctuation ignored).
    support: int = 1


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


def distinct(texts: list[str], scores: list[float], n: int) -> tuple[list[tuple[str, float, int]], list[str]]:
    """The n best hypotheses that differ in words, each with how many beams ended on it, plus the dropped ones."""
    support: dict[str, int] = {}
    for text in texts:
        support[filler_key(text)] = support.get(filler_key(text), 0) + 1
    kept, dropped, seen = [], [], set()
    for text, score in sorted(zip(texts, scores), key=lambda item: item[1], reverse=True):
        key = filler_key(text)
        if key in seen:
            continue
        seen.add(key)
        if not keep_hypothesis(text):
            dropped.append(text.strip())
        elif len(kept) < n:
            kept.append((text.strip(), score, support[key]))
    return kept, dropped


class Whisper:
    """The loaded base model and processor, the active adapter, and a lock so one decode runs at a time."""

    def __init__(self, model, processor, device: str):
        self.model = model
        self.processor = processor
        self.device = device
        self.lock = threading.Lock()
        self.adapter_path: str | None = None
        self.adapters: dict[str, str] = {}
        self.last_split_ms: dict[str, int] = {}
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

    def nbest(self, audio: np.ndarray, n: int = NBEST, stock: bool = False, beams: int = NUM_BEAMS) -> Recognition:
        """Decodes the n best distinct hypotheses (8 beams, temperature 0, English, no timestamps)."""
        with self.lock:
            started = time.perf_counter()
            features = self._features(audio)
            with self._adapter_context(stock):
                encoded = self._encode(features)
                no_speech = self._no_speech_probability(encoded)
                checked = time.perf_counter()
                texts, scores = self._beam_search(features, max(beams, n))
            self.last_split_ms = {"no_speech": round((checked - started) * 1000), "beams": round((time.perf_counter() - checked) * 1000)}
            kept, dropped = distinct(texts, scores, n)
            if no_speech > MAX_NO_SPEECH_PROBABILITY:
                dropped, kept = dropped + [text for text, _, _ in kept], []
            hypotheses = [Hypothesis(text, round(score, 4), support) for text, score, support in kept]
            return Recognition(hypotheses, round(no_speech, 4), dropped, (time.perf_counter() - started) * 1000)

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

    def _encode(self, features):
        """Runs the encoder for the no-speech check (Whisper's generate needs raw features, so it encodes again)."""
        import torch

        with torch.inference_mode():
            return self.model.get_encoder()(features)

    def _no_speech_probability(self, encoded) -> float:
        """The probability of <|nospeech|> right after <|startoftranscript|>, as OpenAI's decoder computes it."""
        import torch

        with torch.inference_mode():
            decoder_ids = torch.tensor([[self.sot_id]], device=self.device)
            logits = self.model(encoder_outputs=encoded, decoder_input_ids=decoder_ids).logits
            return float(torch.softmax(logits[0, -1].float(), dim=-1)[self.no_speech_id])

    def _beam_search(self, features, beams: int) -> tuple[list[str], list[float]]:
        import torch

        with torch.inference_mode():
            out = self.model.generate(
                input_features=features, num_beams=beams, num_return_sequences=beams,
                length_penalty=1.0, do_sample=False, return_dict_in_generate=True, output_scores=True,
                language="en", task="transcribe", max_new_tokens=128,
            )
        texts = self.processor.batch_decode(out.sequences, skip_special_tokens=True)
        return texts, out.sequences_scores.float().tolist()


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
