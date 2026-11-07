"""Checks the call rules where a wrong answer would hurt: μ-law, emergency numbers, Twilio signatures, TwiML, call codes."""

import asyncio
import base64
import json

import numpy as np
import pytest

from voice.calls.codes import MAX_WRONG_CODES, CallCodes, CodeRefused
from voice.calls.mulaw import PhoneAudioDecoder, decode, encode, pulse_tone
from voice.calls.twilio import EMERGENCY_NOTE, PULSE, PhoneError, PhoneLine, check_number, signature, stream_twiml


def test_mulaw_decodes_known_bytes():
    # Reference values from G.711 (the same as Python's old audioop.ulaw2lin).
    assert decode(bytes([0x00, 0x80, 0xFF, 0x7F, 0x0F, 0x8F, 0xCE])).tolist() == [-32124, 32124, 0, 0, -16764, 16764, 988]


def test_mulaw_encodes_known_samples():
    assert encode(np.array([0, 1000, -1000, 32767, -32768])) == bytes([0xFF, 0xCE, 0x4E, 0x80, 0x00])


def test_mulaw_round_trip_stays_within_its_step():
    samples = np.array([-30000, -5000, -100, 0, 7, 250, 4000, 31000], dtype=np.int16)
    restored = decode(encode(samples)).astype(int)
    # μ-law's step is about 3 % of the value (at least 1 near zero), so 4 % or 8 is a safe bound.
    assert np.all(np.abs(restored - samples) <= np.maximum(np.abs(samples) * 0.04, 8))


def test_phone_audio_is_upsampled_to_16k_at_the_same_level():
    t = np.arange(8000) / 8000
    tone = encode(0.3 * 32767 * np.sin(2 * np.pi * 1000 * t))
    decoder = PhoneAudioDecoder()
    wide = np.concatenate([decoder.decode(tone[i : i + 160]) for i in range(0, len(tone), 160)])
    assert wide.size == 16000
    rms = float(np.sqrt(np.mean(wide[1000:] ** 2)))
    assert 0.20 < rms < 0.23  # a 0.3-amplitude sine has RMS 0.212


def test_pulse_tone_is_120_ms_and_quiet():
    pulse = decode(pulse_tone())
    assert pulse.size == 960 and np.abs(pulse).max() < 2500


@pytest.mark.parametrize("number", ["999", "112", "911", "000", "+44 999", "+1 911", "00112", "119", "110"])
def test_emergency_numbers_are_blocked(number):
    with pytest.raises(PhoneError) as refusal:
        check_number(number)
    assert str(refusal.value) == EMERGENCY_NOTE


def test_numbers_are_normalised_to_e164():
    assert check_number("+44 (7700) 900-123") == "+447700900123"
    for bad in ("07700900123", "+0447700900123", "+44", "call me"):
        with pytest.raises(PhoneError):
            check_number(bad)


def test_signature_matches_twilios_documented_example():
    # https://www.twilio.com/docs/usage/security (worked example).
    params = {"CallSid": "CA1234567890ABCDE", "Caller": "+14158675310", "Digits": "1234", "From": "+14158675310", "To": "+18005551212"}
    assert signature("https://example.com/myapp.php?foo=1&bar=2", params, "12345") == "L/OH5YylLD5NRKLltdqwSvS0BnU="


def test_twiml_connects_a_stream_with_the_call_id():
    assert stream_twiml("wss://host.example/twilio/stream", "c-1") == (
        '<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="wss://host.example/twilio/stream">'
        '<Parameter name="call_id" value="c-1"/></Stream></Connect></Response>')


class RecordingSocket:
    """Collects what the server sends on a media stream."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def test_phone_line_pulses_while_he_thinks_then_clears_and_speaks():
    async def scenario():
        line, socket = PhoneLine(http=None, opening_line=""), RecordingSocket()
        line.attach(socket, "MZ1")
        await line.show_state("thinking")
        await asyncio.sleep(0.05)
        await line.play(bytes([0xFF]) * 320)
        return socket.sent

    sent = asyncio.run(scenario())
    pulse = b"".join(base64.b64decode(m["media"]["payload"]) for m in sent[:6])
    assert pulse == PULSE and all(m["streamSid"] == "MZ1" for m in sent)
    assert [m["event"] for m in sent[6:]] == ["clear", "media", "media", "mark"]
    assert sent[-1]["mark"] == {"name": "sentence-1"}


class SettingsRuntime:
    """The two runtime methods CallCodes uses, over an in-memory settings table."""

    def __init__(self):
        self.saved = {"S1": {}, "P1": {}}

    def settings(self, speaker):
        return self.saved[speaker]

    def commit_volumes(self):
        pass


def test_wrong_codes_are_limited_per_client(tmp_path, monkeypatch):
    import voice.calls.codes as codes_module

    monkeypatch.setattr(codes_module, "speaker_dir", lambda speaker: tmp_path / speaker)
    runtime = SettingsRuntime()
    codes = CallCodes(runtime)
    code = codes.code_for("S1")
    runtime.saved["S1"] = json.loads((tmp_path / "S1" / "settings.json").read_text())
    assert len(code) == 6 and codes.code_for("S1") == code and codes.speaker_for(code, "a") == "S1"
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(MAX_WRONG_CODES):
        with pytest.raises(CodeRefused, match="isn't right"):
            codes.speaker_for(wrong, "a")
    with pytest.raises(CodeRefused, match="Too many"):
        codes.speaker_for(code, "a")
    assert codes.speaker_for(code, "b") == "S1"
