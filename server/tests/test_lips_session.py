"""Lips X0 through the real FastAPI app: the flag, lips mode, the camera's socket, its frames and the audio clock."""

import struct

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def frame(seq: int, device_ms: float) -> bytes:
    jpeg = b"\xff\xd8\xff\xd9"
    return struct.pack("<BB2xId4f3f6f8fI", 1, 1, seq, device_ms, *([0.3] * 4), 0.0, 0.0, 0.0,
                       40.0, 18.0, 6.0, 0.15, 0.3, 120.0, *([80.0] * 8), len(jpeg)) + jpeg


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    def make(lips: bool) -> TestClient:
        monkeypatch.setenv("APP_TOKEN", "test-token")
        monkeypatch.setenv("LIPS", "1" if lips else "0")
        import voice.config as config
        import voice.storage as storage

        for module in (config, storage):
            monkeypatch.setattr(module, "DATA_ROOT", tmp_path / "data")
            monkeypatch.setattr(module, "MODELS_ROOT", tmp_path / "models")
        from voice.runtime import Runtime
        from voice.web import create_app

        runtime = Runtime.load()
        client = TestClient(create_app(runtime))
        client.runtime = runtime
        return client

    return make


def hello(ws) -> dict:
    ws.send_json({"type": "hello", "speaker": "P1", "client_version": "t", "settings": {}})
    return ws.receive_json()


def test_lips_mode_is_refused_when_the_flag_is_off(make_client):
    client = make_client(lips=False)
    with client.websocket_connect("/ws?token=test-token") as ws:
        assert hello(ws)["features"]["lips"] is False
        ws.send_json({"type": "lips_mode", "on": True})
        reply = ws.receive_json()
    assert reply == {"type": "lips_mode", "on": False, "reason": "Lip reading is switched off on the server."}


def test_the_camera_socket_needs_lips_mode(make_client):
    client = make_client(lips=True)
    with client.websocket_connect("/ws?token=test-token") as ws:
        hello(ws)
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect("/ws/lips?token=test-token&session_id=nope") as lips:
                lips.receive_text()
    assert closed.value.code == 4404


def test_frames_reach_the_session_ring_and_the_clock_is_fed(make_client):
    client = make_client(lips=True)
    with client.websocket_connect("/ws?token=test-token") as ws:
        hello(ws)
        ws.send_json({"type": "lips_mode", "on": True, "hands_free": False})
        granted = ws.receive_json()
        assert granted["on"] is True and granted["session_id"]
        session = next(iter(client.runtime.sessions))
        with client.websocket_connect(f"/ws/lips?token=test-token&session_id={granted['session_id']}") as lips:
            lips.send_json({"type": "lips_hello", "device": "test browser"})
            for seq in range(5):
                lips.send_bytes(frame(seq, 10_000.0 + 40 * seq))
            lips.send_bytes(b"short")  # malformed: dropped, the stream carries on
            lips.send_json({"type": "lips_bye"})
        ws.send_json({"type": "audio_clock", "samples": 16_000, "device_ms": 11_000.0})
        ws.send_json({"type": "ping"})
        assert session.lips.frames_received == 5 and session.lips.bad_frames == 1
        assert [f.seq for f in session.lips.ring.frames] == [0, 1, 2, 3, 4]
        assert session.lips.clock.device_ms(0) == pytest.approx(10_000.0)
        ws.send_json({"type": "lips_mode", "on": False})
        assert ws.receive_json() == {"type": "lips_mode", "on": False}
        assert session.lips is None
