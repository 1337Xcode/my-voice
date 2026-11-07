"""One live call: his app session on one side, a guest browser or a phone line on the other.

The far side only ever hears his clear synthesised voice; his raw audio never leaves his own session.
"""

import asyncio
import logging
import secrets
from typing import Protocol

from voice.calls.captions import CaptionStream
from voice.config import MissingKey
from voice.tts.elevenlabs import VoiceError, synthesise
from voice.turns.record import now_ms

log = logging.getLogger("voice.calls.call")

STATES = ("dialling", "ringing", "connected", "ended", "failed")


class FarLine(Protocol):
    """The other side of a call: a guest's browser (voice.calls.guest) or a phone line (voice.calls.twilio)."""

    audio_format: str

    async def status(self, message: dict) -> None: ...
    async def before_speaking(self, text: str) -> None: ...
    async def play(self, audio: bytes) -> None: ...
    async def show_state(self, state: str) -> None: ...
    async def close(self, hang_up: bool) -> None: ...


class Call:
    """A call's state, its two sides and the captions of the far side."""

    def __init__(self, kind: str, name: str, far: FarLine, runtime):
        self.id = f"c-{secrets.token_hex(6)}"
        self.kind = kind
        self.name = name
        self.far = far
        self.runtime = runtime
        self.host = None
        self.ringing: set = set()
        self.state = "dialling"
        self.connected_at_ms: int | None = None
        self.captions: CaptionStream | None = None
        self.relay_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()

    def is_live(self) -> bool:
        """True until the call has ended or failed."""
        return self.state not in ("ended", "failed")

    def spawn(self, coroutine) -> None:
        """Runs call work in the background, keeping a reference until it finishes."""
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def status_message(self, state: str, detail: str) -> dict:
        """The `call_status` message both sides get."""
        return {"type": "call_status", "call_id": self.id, "kind": self.kind, "name": self.name, "state": state,
                "detail": detail, "connected_at_ms": self.connected_at_ms}

    async def set_state(self, state: str, detail: str = "", far_detail: str | None = None) -> None:
        """Moves the call to `state` and tells his app (or every ringing device) and the far side."""
        self.state = state
        if state == "connected" and self.connected_at_ms is None:
            self.connected_at_ms = now_ms()
        for session in [self.host] if self.host else list(self.ringing):
            await session.send(self.status_message(state, detail))
        await self.far.status(self.status_message(state, detail if far_detail is None else far_detail))

    async def connect(self) -> None:
        """Both sides are on the line: start captions of the far side and report connected."""
        self.captions = CaptionStream(self.runtime, self.hear, self.caption_failed)
        await self.captions.start()
        await self.set_state("connected")

    async def relay_sentence(self, session, text: str) -> None:
        """Speaks one of his sentences to the far side in his clear voice (called by Session.speak)."""
        async with self.relay_lock:
            if self.state != "connected":
                return
            await self.far.before_speaking(text)
            settings = session.settings()
            try:
                speech = await synthesise(session.runtime.client(), session.speaker, text, session.voice_id(),
                                          self.far.audio_format, float(settings["speech_rate"]))
            except (VoiceError, MissingKey) as error:
                await session.error("call_voice_failed", f"The other side did not hear that sentence. {error}")
                return
            await self.far.play(speech.audio)

    async def his_state(self, session, state: str) -> None:
        """Passes on what he is doing (listening, thinking, choosing, idle) so the far side waits for him."""
        if self.state == "connected" and session is self.host:
            await self.far.show_state(state)

    async def hear(self, text: str) -> None:
        """One caption line from the far side: shown on his screen and kept as conversation context."""
        if self.host is None or not self.is_live():
            return
        await self.host.send({"type": "partner_caption", "call_id": self.id, "text": text, "source": "call"})
        self.host.flow.add_to_conversation("them", text)

    async def caption_failed(self, message: str) -> None:
        """Shows a caption failure in the captions' place; the call itself carries on."""
        if self.host is not None:
            await self.host.error("caption_failed", message)

    def stop(self) -> None:
        """Stops captions and background work once the call is over."""
        if self.captions is not None:
            self.captions.stop()
        for task in list(self.tasks):
            # The ring timer ends the call from inside its own task; cancelling that would cut the ending short.
            if task is not asyncio.current_task():
                task.cancel()
