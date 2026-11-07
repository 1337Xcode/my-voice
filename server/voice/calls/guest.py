"""The guest side of an app call: a friend's browser that dialled his code, over `GET /call/ws?code=…`.

Guest → server: `join {name}`, `hangup_call`, `ping`, and binary frames of 16 kHz mono 16-bit PCM from their mic.
Server → guest: `call_status`, `peer_state`, `sentence {text}`, `audio {format, data}`.
"""

import base64
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from voice.audio.pcm import pcm16_to_float
from voice.calls.codes import CodeRefused
from voice.tts.elevenlabs import APP_FORMAT

log = logging.getLogger("voice.calls.guest")

NAME_MAX_CHARS = 40
# One second of 16 kHz 16-bit audio; the client sends 100 ms frames, so anything bigger is not mic audio.
MAX_FRAME_BYTES = 32_000


class GuestLine:
    """The guest's browser as the far side of a call: it shows his sentences and plays them in his voice."""

    audio_format = APP_FORMAT

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.closed = False
        self.call = None

    async def send(self, message: dict) -> None:
        """Sends one JSON message; a closed socket drops it."""
        if self.closed:
            return
        try:
            await self.ws.send_text(json.dumps(message))
        except (RuntimeError, WebSocketDisconnect):
            log.info("guest socket closed; dropped %s", message.get("type"))

    async def status(self, message: dict) -> None:
        await self.send(message)

    async def before_speaking(self, text: str) -> None:
        """Shows his sentence straight away, while the voice is still being made."""
        await self.send({"type": "sentence", "text": text})

    async def play(self, audio: bytes) -> None:
        await self.send({"type": "audio", "format": APP_FORMAT, "data": base64.b64encode(audio).decode("ascii")})

    async def show_state(self, state: str) -> None:
        await self.send({"type": "peer_state", "state": state})

    async def close(self, hang_up: bool) -> None:
        """Closes the guest's socket after the final call_status."""
        if self.closed:
            return
        self.closed = True
        try:
            await self.ws.close()
        except RuntimeError:
            pass


def client_address(ws: WebSocket) -> str:
    """The caller's address for wrong-code limiting (the first forwarded address behind the proxy)."""
    forwarded = ws.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (ws.client.host if ws.client else "unknown")


def guest_name(message: dict) -> str:
    """The name the guest typed, tidied, or a neutral one."""
    name = " ".join(str(message.get("name") or "").split())[:NAME_MAX_CHARS]
    return name or "Someone"


async def run_guest(ws: WebSocket, runtime, code: str) -> None:
    """Serves one guest connection: checks the code, rings him on `join`, bridges the call until either side ends it."""
    await ws.accept()
    line = GuestLine(ws)
    try:
        speaker = runtime.calls.codes.speaker_for(code.strip(), client_address(ws))
    except CodeRefused as refusal:
        await line.send({"type": "call_status", "call_id": None, "state": "failed", "detail": str(refusal)})
        await line.close(hang_up=False)
        return
    log.info("guest connected for %s", speaker)
    try:
        await _serve(ws, runtime, speaker, line)
    except (WebSocketDisconnect, RuntimeError):
        pass  # The guest's connection dropped (or was closed after the call ended).
    finally:
        if line.call is not None and line.call.is_live():
            await runtime.calls.guest_left(line.call)


async def _serve(ws: WebSocket, runtime, speaker: str, line: GuestLine) -> None:
    """The guest's message loop, until the guest leaves or the call ends; the call is kept on `line.call`."""
    while not line.closed:
        message = await ws.receive()
        call = line.call
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes") is not None:
            frame = message["bytes"]
            if call is not None and call.state == "connected" and call.captions is not None and len(frame) <= MAX_FRAME_BYTES:
                call.captions.add(pcm16_to_float(frame))
            continue
        request = _read(message.get("text") or "")
        kind = request.get("type")
        if kind == "join" and call is None:
            line.call = call = await runtime.calls.ring(speaker, guest_name(request), line)
            if not call.is_live():
                await line.close(hang_up=False)
        elif kind == "hangup_call" and call is not None:
            await runtime.calls.guest_left(call)
        elif kind not in ("ping", "join", "hangup_call"):
            await line.send({"type": "error", "code": "unknown_type", "message": f"The call does not handle {kind!r} messages."})


def _read(raw: str) -> dict:
    """One guest JSON message as a dict ({} when unreadable)."""
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return message if isinstance(message, dict) else {}
