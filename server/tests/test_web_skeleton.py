"""Checks the skeleton's routes and the hello/ready handshake against the real FastAPI app."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_TOKEN", "test-token")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-1")
    import voice.config as config

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(config, "MODELS_ROOT", tmp_path / "models")
    import voice.storage as storage

    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(storage, "MODELS_ROOT", tmp_path / "models")
    from voice.runtime import Runtime
    from voice.web import create_app

    return TestClient(create_app(Runtime.load()))


def test_health_needs_no_token(client):
    assert client.get("/health").json()["ok"] is True


def test_wake_rejects_a_wrong_token(client):
    assert client.post("/wake", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_hello_gets_ready_with_voice_and_features(client):
    with client.websocket_connect("/ws?token=test-token") as ws:
        ws.send_json({"type": "hello", "speaker": "P1", "client_version": "t", "settings": {}})
        ready = ws.receive_json()
    assert ready == {"type": "ready", "speaker": "P1", "model_version": "stock", "voice_id": "JBFqnCBsd6RMkjVDRZzb", "features": {"calls": False, "toolkit": False, "partials": False}}


def test_unknown_speaker_gets_a_plain_error(client):
    with client.websocket_connect("/ws?token=test-token") as ws:
        ws.send_json({"type": "hello", "speaker": "X9"})
        message = ws.receive_json()
    assert message["type"] == "error" and "unknown speaker" in message["message"]


def test_phrases_are_seeded_from_the_default_bank(client):
    phrases = client.get("/phrases?speaker=P1", headers={"Authorization": "Bearer test-token"}).json()["phrases"]
    assert len(phrases) == 29
    assert phrases[0] == {"id": "p01", "text": "Hello, nice to meet you.", "category": "Social", "order": 1, "pinned": False, "template_clip_ids": [], "tts": {}, "uses": 0}
