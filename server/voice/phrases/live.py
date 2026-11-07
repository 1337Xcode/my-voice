"""The serving container's phrase matchers: one shared WavLM, one template set per speaker, refreshed on change."""

import logging
import threading

import numpy as np

from voice.phrases.matcher import MatchResult, PhraseMatcher, load_templates

log = logging.getLogger("voice.phrases.live")


class LiveMatchers:
    """Holds the encoder once and builds each speaker's matcher on first use."""

    def __init__(self, model, extractor, device: str, trim):
        self.model, self.extractor, self.device, self.trim = model, extractor, device, trim
        self.matchers: dict[str, PhraseMatcher] = {}
        self.lock = threading.Lock()

    def matcher(self, speaker: str) -> PhraseMatcher:
        """The speaker's matcher, loading his templates from the volume the first time."""
        with self.lock:
            if speaker not in self.matchers:
                matcher = PhraseMatcher(self.model, self.extractor, self.device, trim=self.trim)
                matcher.set_templates(load_templates(speaker))
                self.matchers[speaker] = matcher
            return self.matchers[speaker]

    def reload(self, speaker: str) -> None:
        """Forgets the speaker's matcher so the next turn rebuilds it from the bank (after edits or imports)."""
        with self.lock:
            self.matchers.pop(speaker, None)

    def match(self, speaker: str, audio: np.ndarray) -> MatchResult | None:
        """Matches one utterance against his phrases, or None when he has no recorded phrases yet."""
        matcher = self.matcher(speaker)
        with self.lock:
            if not matcher.has_templates:
                return None
            return matcher.match(audio)

    def add_template(self, speaker: str, phrase_id: str, text: str, audio: np.ndarray) -> None:
        """Adds a fresh recording of a phrase (keeps the 5 most recent)."""
        matcher = self.matcher(speaker)
        with self.lock:
            matcher.add_template(phrase_id, text, audio)


def load_live_matchers(device: str) -> LiveMatchers:
    """Loads WavLM and the VAD trimmer on the serving GPU."""
    from voice.phrases.features import load_wavlm, make_silero_trim

    model, extractor = load_wavlm(device)
    return LiveMatchers(model, extractor, device, make_silero_trim())
