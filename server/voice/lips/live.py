"""A session's lips (EXP X0): the frame stream from `/ws/lips`, its clock, per-turn frame windows and the sync check."""

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from voice.lips.frames import BadFrame, LipFrame, parse_frame
from voice.lips.store import device_key, load_lips, save_lips
from voice.lips.sync import estimate_offset
from voice.lips.timeline import MS_PER_SAMPLE, AudioClock, FrameRing

if TYPE_CHECKING:
    from voice.session import Session
    from voice.turns.turn import Turn

log = logging.getLogger("voice.lips")


class LipSession:
    """Lips mode for one app session: on while the lips screen is open."""

    def __init__(self, session: "Session", hands_free: bool):
        self.session = session
        self.hands_free = hands_free
        self.ring = FrameRing()
        self.clock = AudioClock()
        self.device: str | None = None
        self.offset_ms = 0.0
        self.frames_received = 0
        self.bad_frames = 0
        self.streaming = False
        # Each turn's first audio sample, counted over the whole session.
        self.turn_starts: dict[str, int] = {}

    def hello(self, message: dict) -> None:
        """The camera connected: remember the device and use its stored sync offset."""
        self.device = device_key(str(message.get("device") or "unknown"))
        stored = load_lips(self.session.speaker).get("devices", {}).get(self.device, {})
        self.offset_ms = float(stored.get("offset_ms", 0.0))

    def add(self, data: bytes) -> None:
        try:
            frame = parse_frame(data)
        except BadFrame as error:
            self.bad_frames += 1
            if self.bad_frames <= 3:
                log.warning("lip frame dropped: %s", error)
            return
        self.frames_received += 1
        self.ring.add(frame)

    def turn_started(self, turn: "Turn", session_sample: int) -> None:
        self.turn_starts[turn.id] = session_sample

    def audio_start_ms(self, turn: "Turn") -> float | None:
        """Device time of the turn's first sample, or None before the clock has a report."""
        start = self.turn_starts.get(turn.id)
        return None if start is None else self.clock.device_ms(start)

    def turn_frames(self, turn: "Turn") -> list[LipFrame]:
        """The frames that line up with the turn's audio, after the device's sync offset."""
        start_ms = self.audio_start_ms(turn)
        if start_ms is None:
            return []
        end_ms = start_ms + turn.audio.total * MS_PER_SAMPLE
        return self.ring.between(start_ms - self.offset_ms, end_ms - self.offset_ms)

    def summary(self, turn: "Turn") -> dict:
        """Capture stats for the turn record (EXP-SPEC 9.1)."""
        frames = self.turn_frames(turn)
        seconds = max(turn.audio.total * MS_PER_SAMPLE / 1000, 1e-6)
        visible = sum(1 for f in frames if f.face_visible)
        return {"frames": len(frames), "fps": round(len(frames) / seconds, 1),
                "face_visible_pct": round(100 * visible / len(frames), 1) if frames else 0.0,
                "offset_ms": self.offset_ms, "clock": self.clock.ready()}

    async def sync_check(self, turn: "Turn") -> None:
        """'pa pa pa pa pa': measures and stores this device's audio-video offset, then reports it (lips_setup)."""
        start_ms = self.audio_start_ms(turn)
        if start_ms is None or self.device is None:
            await self._setup("sync", False, "The camera isn't connected yet. Wait for the green ring, then try again.")
            return
        end_ms = start_ms + turn.audio.total * MS_PER_SAMPLE
        frames = [f for f in self.ring.between(start_ms - 600, end_ms + 600) if f.face_visible]
        frame_ms = np.array([f.device_ms for f in frames], dtype=float)
        opening = np.array([f.mouth_aspect for f in frames], dtype=float)
        result = await asyncio.to_thread(estimate_offset, turn.audio.audio(), start_ms, frame_ms, opening)
        turn.record.exp["lips_sync"] = {"ok": result.ok, "offset_ms": result.offset_ms, "correlation": result.correlation, "bursts": result.bursts}
        if result.ok:
            self.offset_ms = result.offset_ms
            await asyncio.to_thread(self._store_offset, result.offset_ms, result.correlation)
        await self._setup("sync", result.ok, result.reason, offset_ms=result.offset_ms)

    def _store_offset(self, offset_ms: float, correlation: float) -> None:
        data = load_lips(self.session.speaker)
        data.setdefault("devices", {})[self.device] = {"offset_ms": offset_ms, "correlation": correlation, "at": int(time.time())}
        save_lips(self.session.speaker, data)
        self.session.runtime.commit_volumes()

    async def _setup(self, step: str, ok: bool, reason: str | None, **extra) -> None:
        await self.session.send({"type": "lips_setup", "step": step, "ok": ok, "reason": reason, **extra})


async def run_lip_stream(ws: WebSocket, session: "Session") -> None:
    """Serves one `/ws/lips` connection: binary frames into the session's ring, `lips_hello` and `lips_bye`."""
    lips = session.lips
    lips.streaming = True
    try:
        while session.lips is lips:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                lips.add(message["bytes"])
            elif message.get("text") is not None:
                text = _json(message["text"])
                if text.get("type") == "lips_hello":
                    await asyncio.to_thread(lips.hello, text)
                elif text.get("type") == "lips_bye":
                    return
    except WebSocketDisconnect:
        return
    finally:
        lips.streaming = False


def _json(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
