"""Runs calls end to end through the real FastAPI app: a guest dialling his code, and a phone call over Twilio's stream.

The recogniser (a GPU model) and Twilio's REST API are replaced by recorded responses; the VAD, μ-law, routing,
signatures and the session protocol are the real code.
"""

import base64
from urllib.parse import parse_qs

import httpx
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice.asr.whisper import Hypothesis, Recognition

AUTH = {"Authorization": "Bearer test-token"}
FIXTURE = "tests/fixtures/hello_caller.wav"
HEARD = "Hello, it's lovely to hear from you."
TWILIO_TOKEN = "twilio-test-token"


class RecordedRecogniser:
    """Stands in for the GPU recogniser: replays one recorded transcript and notes how it was asked."""

    adapter_path = None

    def __init__(self):
        self.requests: list[tuple[int, int, bool]] = []

    def nbest(self, audio, n=8, stock=False, beams=8):
        self.requests.append((audio.size, n, stock))
        return Recognition([Hypothesis(HEARD, -0.2)], 0.01, [], 1.0)


def recorded_twilio(requests: list[httpx.Request]):
    """Twilio's REST responses for creating and ending a call, as recorded from its Call resource docs."""

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = "completed" if request.url.path.endswith("/CA0123.json") else "queued"
        return httpx.Response(201, json={"sid": "CA0123", "status": status, "to": "+447700900123"})

    return respond


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_TOKEN", "test-token")
    for variable in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    import voice.config as config
    import voice.storage as storage

    for module in (config, storage):
        monkeypatch.setattr(module, "DATA_ROOT", tmp_path / "data")
        monkeypatch.setattr(module, "MODELS_ROOT", tmp_path / "models")
    from voice.calls.routes import router
    from voice.runtime import Runtime
    from voice.web import create_app

    runtime = Runtime.load()
    runtime.whisper = RecordedRecogniser()
    app = create_app(runtime)
    if not any(getattr(route, "path", None) == "/call/ws" for route in app.routes):
        app.include_router(router)
    return app, runtime


def use_twilio(monkeypatch, runtime) -> list[httpx.Request]:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC0001")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TWILIO_TOKEN)
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550001111")
    requests: list[httpx.Request] = []
    runtime.http = httpx.AsyncClient(transport=httpx.MockTransport(recorded_twilio(requests)))
    return requests


def cache_voice(text: str, fmt: str, audio: bytes) -> None:
    """Puts a recorded voice clip where synthesise() looks first, so no ElevenLabs call is made."""
    from voice.tts.elevenlabs import cache_path, voices

    path = cache_path("S1", voices()["default"], fmt, f"1.00|{text}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)


def speech_with_pause() -> np.ndarray:
    audio, rate = sf.read(FIXTURE, dtype="float32")
    assert rate == 16000
    return np.concatenate([audio, np.zeros(24000, dtype=np.float32)])


def say_hello(host) -> None:
    host.send_json({"type": "hello", "speaker": "S1", "settings": {}})
    assert host.receive_json()["type"] == "ready"


def test_guest_call_bridges_captions_and_his_voice(setup):
    app, runtime = setup
    from voice.tts.elevenlabs import APP_FORMAT

    cache_voice("Lovely to hear you too.", APP_FORMAT, b"\xff\xfb\x90\x00" * 64)
    with TestClient(app) as client:
        code = client.post("/calls/link?speaker=S1", headers=AUTH).json()["code"]
        with client.websocket_connect("/ws?token=test-token") as host:
            say_hello(host)
            with client.websocket_connect(f"/call/ws?code={code}") as guest:
                guest.send_json({"type": "join", "name": "  Sam  "})
                assert guest.receive_json()["state"] == "ringing"
                incoming = host.receive_json()
                assert incoming == {"type": "incoming_call", "call_id": incoming["call_id"], "name": "Sam", "kind": "app"}
                host.send_json({"type": "answer_call", "call_id": incoming["call_id"]})
                his, theirs = host.receive_json(), guest.receive_json()
                assert his["state"] == theirs["state"] == "connected" and his["connected_at_ms"] == theirs["connected_at_ms"]

                host.send_json({"type": "start_turn", "turn_id": "t1", "mode": "call"})
                assert guest.receive_json() == {"type": "peer_state", "state": "listening"}

                pcm = (speech_with_pause() * 32767).astype("<i2").tobytes()
                for start in range(0, len(pcm), 3200):  # 100 ms frames
                    guest.send_bytes(pcm[start : start + 3200])
                caption = host.receive_json()
                assert caption == {"type": "partner_caption", "call_id": incoming["call_id"], "text": HEARD, "source": "call"}
                samples, n, stock = runtime.whisper.requests[0]
                assert (n, stock) == (1, True) and 16000 < samples < 48000
                session = next(iter(runtime.sessions))
                assert {"who": "them", "text": HEARD} in session.flow.conversation

                host.send_json({"type": "type_and_speak", "text": "Lovely to hear you too."})
                assert host.receive_json()["type"] == "audio"
                assert guest.receive_json() == {"type": "sentence", "text": "Lovely to hear you too."}
                heard = guest.receive_json()
                assert heard["type"] == "audio" and base64.b64decode(heard["data"]) == b"\xff\xfb\x90\x00" * 64

                guest.send_json({"type": "hangup_call"})
                assert host.receive_json()["detail"] == "Sam hung up."
                assert guest.receive_json()["state"] == "ended"
    assert runtime.calls.calls == {}


def test_guest_gets_a_plain_answer_when_he_is_not_connected(setup):
    app, _ = setup
    with TestClient(app) as client:
        code = client.post("/calls/link?speaker=S1", headers=AUTH).json()["code"]
        with client.websocket_connect(f"/call/ws?code={code}") as guest:
            guest.send_json({"type": "join", "name": "Sam"})
            status = guest.receive_json()
    assert (status["state"], status["detail"]) == ("failed", "They're not available right now.")


def test_declined_and_missed_calls(setup, monkeypatch):
    app, _ = setup
    import voice.calls.manager as manager

    monkeypatch.setattr(manager, "RING_TIMEOUT_S", 0.2)
    with TestClient(app) as client:
        code = client.post("/calls/link?speaker=S1", headers=AUTH).json()["code"]
        with client.websocket_connect("/ws?token=test-token") as host:
            say_hello(host)
            with client.websocket_connect(f"/call/ws?code={code}") as guest:
                guest.send_json({"type": "join", "name": "Sam"})
                guest.receive_json()
                host.send_json({"type": "decline_call", "call_id": host.receive_json()["call_id"]})
                assert host.receive_json()["detail"] == "Declined."
                assert guest.receive_json()["detail"] == "They can't take the call right now."
            with client.websocket_connect(f"/call/ws?code={code}") as guest:
                guest.send_json({"type": "join", "name": "Sam"})
                guest.receive_json()
                assert host.receive_json()["type"] == "incoming_call"
                missed = guest.receive_json()
                assert (missed["state"], missed["detail"]) == ("failed", "No answer.")
                assert host.receive_json()["detail"] == "Missed call from Sam."


def test_regenerated_code_replaces_the_old_one(setup):
    app, _ = setup
    with TestClient(app) as client:
        old = client.post("/calls/link?speaker=S1", headers=AUTH).json()
        new = client.post("/calls/code/regenerate?speaker=S1", headers=AUTH).json()
        assert new["url_path"] == f"/c/{new['code']}" and new["code"] != old["code"]
        with client.websocket_connect(f"/call/ws?code={old['code']}") as guest:
            assert "isn't right" in guest.receive_json()["detail"]


def test_phone_call_refuses_emergency_numbers_and_names_missing_keys(setup):
    app, _ = setup
    with TestClient(app) as client:
        blocked = client.post("/calls?speaker=S1", headers=AUTH, json={"number": "999", "name": "x"})
        missing = client.post("/calls?speaker=S1", headers=AUTH, json={"number": "+447700900123"})
    assert blocked.status_code == 400 and "emergencySMS" in blocked.json()["detail"]
    assert missing.status_code == 503 and missing.json()["missing"] == "TWILIO_ACCOUNT_SID"


def signed(url: str, params: dict) -> dict:
    from voice.calls.twilio import signature

    return {"X-Twilio-Signature": signature(url, params, TWILIO_TOKEN)}


def test_phone_call_end_to_end(setup, monkeypatch):
    app, runtime = setup
    requests = use_twilio(monkeypatch, runtime)
    from voice.calls.mulaw import encode
    from voice.audio.pcm import resample
    from voice.tts.elevenlabs import CALL_FORMAT

    cache_voice("Hi, it's me.", CALL_FORMAT, encode(np.full(4000, 1000)))
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=test-token") as host:
            say_hello(host)
            started = client.post("/calls?speaker=S1", headers=AUTH, json={"number": "+44 7700 900123", "name": "Sam", "opening_line": "Hi, it's me."})
            call_id = started.json()["call_id"]
            assert host.receive_json()["state"] == "dialling"
            sent = parse_qs(requests[0].content.decode())
            assert sent["To"] == ["+447700900123"] and sent["From"] == ["+15550001111"]
            assert sent["Url"] == [f"https://testserver/twilio/voice?call_id={call_id}"]
            assert sent["StatusCallbackEvent"] == ["initiated", "ringing", "answered", "completed"]

            status_url = f"https://testserver/twilio/status?call_id={call_id}"
            ringing = {"CallSid": "CA0123", "CallStatus": "ringing"}
            assert client.post(f"/twilio/status?call_id={call_id}", data=ringing, headers=signed(status_url, ringing)).status_code == 204
            assert host.receive_json()["state"] == "ringing"

            voice_url = f"https://testserver/twilio/voice?call_id={call_id}"
            answered = {"CallSid": "CA0123", "CallStatus": "in-progress"}
            assert client.post(f"/twilio/voice?call_id={call_id}", data=answered).status_code == 403
            twiml = client.post(f"/twilio/voice?call_id={call_id}", data=answered, headers=signed(voice_url, answered)).text
            assert f'<Stream url="wss://testserver/twilio/stream"><Parameter name="call_id" value="{call_id}"/>' in twiml

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/twilio/stream", headers={"X-Twilio-Signature": "wrong"}) as stream:
                    stream.receive_json()
            with client.websocket_connect("/twilio/stream", headers=signed("wss://testserver/twilio/stream", {})) as stream:
                stream.send_json({"event": "connected", "protocol": "Call", "version": "1.0.0"})
                stream.send_json({"event": "start", "sequenceNumber": "1", "streamSid": "MZ1",
                                  "start": {"streamSid": "MZ1", "callSid": "CA0123", "tracks": ["inbound"], "customParameters": {"call_id": call_id}}})
                assert host.receive_json()["state"] == "connected"
                opening = [stream.receive_json() for _ in range(27)]
                assert [m["event"] for m in opening] == ["clear"] + ["media"] * 25 + ["mark"]

                phone = encode(resample(speech_with_pause(), 16000, 8000) * 32767)
                for start in range(0, len(phone), 160):  # 20 ms, as Twilio sends
                    payload = base64.b64encode(phone[start : start + 160]).decode()
                    stream.send_json({"event": "media", "streamSid": "MZ1", "media": {"track": "inbound", "payload": payload}})
                assert host.receive_json()["text"] == HEARD
                assert runtime.whisper.requests[0][2] is True

                assert client.post(f"/calls/{call_id}/hangup", headers=AUTH).json()["state"] == "ended"
                assert host.receive_json()["detail"] == "Call ended."
            assert parse_qs(requests[-1].content.decode()) == {"Status": ["completed"]}
    assert runtime.calls.calls == {}


def answer_guest(host, guest) -> None:
    """The guest joins, he answers, and both see the call connect."""
    guest.send_json({"type": "join", "name": "Sam"})
    assert guest.receive_json()["state"] == "ringing"
    host.send_json({"type": "answer_call", "call_id": host.receive_json()["call_id"]})
    assert host.receive_json()["state"] == guest.receive_json()["state"] == "connected"


def test_a_dropped_connection_ends_the_call_for_the_other_side(setup):
    app, runtime = setup
    with TestClient(app) as client:
        code = client.post("/calls/link?speaker=S1", headers=AUTH).json()["code"]
        with client.websocket_connect("/ws?token=test-token") as host:
            say_hello(host)
            with client.websocket_connect(f"/call/ws?code={code}") as guest:
                answer_guest(host, guest)
            assert host.receive_json()["detail"] == "Sam hung up."
        with client.websocket_connect(f"/call/ws?code={code}") as guest:
            with client.websocket_connect("/ws?token=test-token") as host:
                say_hello(host)
                answer_guest(host, guest)
            assert guest.receive_json()["detail"] == "The call dropped."
    assert runtime.calls.calls == {}
