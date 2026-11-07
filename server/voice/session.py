"""One app WebSocket session: reads client messages and answers them (spec section 12.1)."""

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from voice.config import SPEAKERS, default_voice_id, features
from voice.runtime import Runtime

log = logging.getLogger("voice.session")


class Session:
    """The state of one connected app, from its hello until it disconnects."""

    def __init__(self, ws: WebSocket, runtime: Runtime):
        self.ws = ws
        self.runtime = runtime
        self.speaker: str | None = None

    async def send(self, message: dict) -> None:
        """Sends one JSON message to the app."""
        await self.ws.send_text(json.dumps(message))

    async def error(self, code: str, message: str) -> None:
        """Sends a plain-language error the app can show as it is."""
        await self.send({"type": "error", "code": code, "message": message})

    async def on_hello(self, message: dict) -> None:
        """Session start or reconnect: remember the speaker and report readiness."""
        speaker = message.get("speaker")
        if speaker not in SPEAKERS:
            await self.error("bad_speaker", f"The app asked for an unknown speaker. Use one of {', '.join(SPEAKERS)}.")
            return
        self.speaker = speaker
        await self.send({
            "type": "ready",
            "speaker": speaker,
            "model_version": self.runtime.model_version(speaker),
            "voice_id": default_voice_id(),
            "features": features().as_dict(),
        })

    async def on_ping(self, _message: dict) -> None:
        """Keepalive from the app; receiving it is enough."""

    async def on_text(self, raw: str) -> None:
        """Routes one JSON message to its handler by type."""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            await self.error("bad_message", "The server got a message it could not read.")
            return
        handler = getattr(self, f"on_{message.get('type', '')}", None)
        if handler is None:
            await self.error("unknown_type", f"The server does not handle {message.get('type')!r} messages yet.")
            return
        await handler(message)

    async def on_audio(self, _frame: bytes) -> None:
        """Binary audio frames: the core loop (phase 1) consumes these."""


async def run_session(ws: WebSocket, runtime: Runtime) -> None:
    """Serves one app connection until it closes."""
    session = Session(ws, runtime)
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await session.on_audio(message["bytes"])
            elif message.get("text") is not None:
                await session.on_text(message["text"])
    except WebSocketDisconnect:
        return
