"""Checks end-of-speech and speculative-start decisions from per-window speech probabilities (spec 8.2)."""

from voice.audio.endpointing import TurnAudio


class _NoState:
    """Stands in for Silero's state reset; the tests feed probabilities directly."""

    def reset_states(self):
        pass


def feed(audio: TurnAudio, probabilities: list[float]) -> None:
    for probability in probabilities:
        audio._score(probability)


def test_turn_ends_after_the_configured_silence_following_enough_speech():
    audio = TurnAudio(vad_model=_NoState(), silence_ms=900)
    feed(audio, [0.9] * 10 + [0.1] * 28)  # 320 ms of speech, then 896 ms of silence
    assert not audio.ended_by_silence()
    feed(audio, [0.1])  # 928 ms of silence
    assert audio.ended_by_silence()


def test_under_250_ms_of_speech_is_too_short_and_never_ends_by_silence():
    audio = TurnAudio(vad_model=_NoState(), silence_ms=500)
    feed(audio, [0.9] * 7 + [0.1] * 40)  # 224 ms of speech
    assert audio.too_short() and not audio.ended_by_silence()


def test_speculation_starts_once_per_pause_and_again_after_new_speech():
    audio = TurnAudio(vad_model=_NoState(), silence_ms=900)
    feed(audio, [0.9] * 10 + [0.1] * 10)  # 320 ms silence after speech
    assert audio.pause_started()
    assert not audio.pause_started()
    feed(audio, [0.9] * 5 + [0.1] * 10)
    assert audio.pause_started()
