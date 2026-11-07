"""One app WebSocket session: the message protocol of spec 12.1, routed to the turn flow and the voice."""

import asyncio
import base64
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from voice.audio.endpointing import TurnAudio
from voice.audio.pcm import pcm16_to_float
from voice.config import SPEAKERS, MissingKey, features
from voice.http.settings_model import valid_settings
from voice.runtime import Runtime
from voice.tts.elevenlabs import APP_FORMAT, VoiceError, synthesise, voices
from voice.turns.flow import TurnFlow
from voice.turns.record import TurnRecord, now_ms
from voice.turns.turn import MODES, Turn

log = logging.getLogger("voice.session")



class Session:
    """The state of one connected app, from its hello until it disconnects."""

    def __init__(self, ws: WebSocket, runtime: Runtime):
        self.ws = ws
        self.runtime = runtime
        self.speaker: str | None = None
        self.turn: Turn | None = None
        self.flow = TurnFlow(self)
        self.vad_model = None
        self.send_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        # The live call this session is in (voice.calls), or None.
        self.call = None

    async def send(self, message: dict) -> None:
        """Sends one JSON message to the app; a closed socket is ignored."""
        try:
            async with self.send_lock:
                await self.ws.send_text(json.dumps(message))
        except (RuntimeError, WebSocketDisconnect):
            log.info("send after close dropped: %s", message.get("type"))

    async def error(self, code: str, message: str) -> None:
        """Sends a plain-language error the app can show as it is."""
        await self.send({"type": "error", "code": code, "message": message})

    def spawn(self, coroutine) -> None:
        """Runs work in the background, keeping a reference and logging failures."""
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("session task failed", exc_info=task.exception())

    def settings(self) -> dict:
        return self.runtime.settings(self.speaker or "P1")

    def voice_id(self) -> str:
        """His chosen voice, or the default mature male voice."""
        return self.settings().get("voice_id") or voices()["default"]

    async def on_hello(self, message: dict) -> None:
        """Session start or reconnect: remember the speaker, apply his settings and report readiness."""
        speaker = message.get("speaker")
        if speaker not in SPEAKERS:
            await self.error("bad_speaker", f"The app asked for an unknown speaker. Use one of {', '.join(SPEAKERS)}.")
            return
        self.speaker = speaker
        change = valid_settings(message.get("settings") or {})
        if change:
            await asyncio.to_thread(self.runtime.save_settings, speaker, change)
        self.runtime.background(self.runtime.warm_connections())
        version = await asyncio.to_thread(self.runtime.ensure_adapter, speaker)
        await self.send({"type": "ready", "speaker": speaker, "model_version": version, "voice_id": self.voice_id(), "features": features().as_dict()})

    async def on_ping(self, _message: dict) -> None:
        """Keepalive from the app; receiving it is enough."""

    async def on_start_turn(self, message: dict) -> None:
        """Opens a turn; the binary frames that follow are its audio."""
        if not await self._require_hello():
            return
        mode = message.get("mode", "talk")
        turn_id = str(message.get("turn_id") or f"t-{now_ms()}")
        if mode not in MODES:
            await self.error("bad_mode", f"Unknown turn mode {mode!r}.")
            return
        if self.vad_model is None:
            from silero_vad import load_silero_vad

            self.vad_model = await asyncio.to_thread(load_silero_vad)
        record = TurnRecord(turn_id=turn_id, speaker=self.speaker, mode=mode, model_version=self.runtime.model_version(self.speaker))
        silence_ms = int(self.settings()["endpoint_silence_ms"])
        self.turn = Turn(record=record, audio=TurnAudio(vad_model=self.vad_model, silence_ms=silence_ms))
        await self.peer_state("listening")

    async def on_audio(self, frame: bytes) -> None:
        """One binary audio frame for the open turn; ends the turn when the VAD hears the end of speech."""
        turn = self.turn
        if turn is None or turn.state != "listening":
            return
        if turn.record.t_first_audio is None:
            turn.record.mark("t_first_audio")
        if turn.audio.add(pcm16_to_float(frame)):
            turn.record.end_reason = "silence" if turn.audio.ended_by_silence() else "max_length"
            await self.send({"type": "endpoint", "turn_id": turn.id})
            self._finish_listening(turn)
        elif turn.audio.pause_started():
            self.flow.speculate(turn)
        elif self.wants_partials(turn):
            self.flow.partial(turn)

    def wants_partials(self, turn: Turn) -> bool:
        """Live words only with his personal model (stock partials on his speech are noise) and when he asked for them."""
        return (turn.mode in ("talk", "call", "tell") and bool(self.settings().get("partials"))
                and turn.record.model_version != "stock" and turn.audio.partial_due())

    async def on_end_turn(self, message: dict) -> None:
        """He tapped Done: the turn ends now."""
        turn = self.turn
        if turn and turn.id == message.get("turn_id") and turn.state == "listening":
            turn.record.end_reason = "done"
            self._finish_listening(turn)

    def _finish_listening(self, turn: Turn) -> None:
        turn.state = "processing"
        turn.record.mark("t_end_of_speech")
        self.spawn(self.flow.process(turn))

    async def on_cancel_turn(self, message: dict) -> None:
        """Discards the open turn."""
        turn = self.turn
        if turn and turn.id == message.get("turn_id"):
            turn.state = "finished"
            turn.record.outcome = "cancelled"
            await asyncio.to_thread(turn.record.save)
            self.turn = None

    async def on_choose(self, message: dict) -> None:
        """His explicit pick or typed sentence for a turn: speak it and learn from it."""
        await self.flow.choose(message.get("turn_id"), message.get("candidate_id"), message.get("text"), message.get("via", "pick"))

    async def on_confirm(self, message: dict) -> None:
        """The check on a check-first card: speak the top candidate."""
        await self.flow.confirm(message.get("turn_id"))

    async def on_reject(self, message: dict) -> None:
        """'Not what I meant' on a spoken sentence."""
        await self.flow.reject(message.get("turn_id"))

    async def on_type_and_speak(self, message: dict) -> None:
        """A typed sentence, spoken straight away."""
        text = str(message.get("text", "")).strip()
        if text and await self._require_hello():
            await self.speak(text, turn_id=message.get("turn_id"))

    async def on_say_phrase(self, message: dict) -> None:
        """One-tap phrase: speak the cached audio."""
        if await self._require_hello():
            await self.flow.say_phrase(str(message.get("phrase_id", "")))

    async def on_client_timing(self, message: dict) -> None:
        """The app's measured end-to-text and end-to-audio times for a turn."""
        await self.flow.client_timing(message)

    async def speak(self, text: str, turn_id: str | None = None, phrase_id: str | None = None, record: TurnRecord | None = None) -> bool:
        """Synthesises text in his voice and sends it as one `audio` message; returns False on failure."""
        started_ms = now_ms()
        try:
            speech = await synthesise(self.runtime.client(), self.speaker, text, self.voice_id(), APP_FORMAT, float(self.settings()["speech_rate"]))
        except (VoiceError, MissingKey) as error:
            await self.error("voice_failed", str(error))
            if record is not None:
                record.errors.append(f"tts: {error}")
            return False
        if record is not None:
            record.t_tts_first_byte = started_ms + int(speech.first_byte_ms)
            record.mark("t_tts_done")
        target = {"phrase_id": phrase_id} if phrase_id else {"turn_id": turn_id}
        if self.call is not None:
            # In a call the other side hears the sentence too; this runs alongside the local playback.
            self.spawn(self.call.relay_sentence(self, text))
        await self.send({"type": "audio", **target, "format": APP_FORMAT, "text": text, "data": base64.b64encode(speech.audio).decode("ascii")})
        return True

    async def peer_state(self, state: str) -> None:
        """Tells the other side of a call what he is doing (listening, thinking, idle), so they wait for him."""
        if self.call is not None:
            await self.call.his_state(self, state)

    async def _require_hello(self) -> bool:
        if self.speaker is None:
            await self.error("no_hello", "The app has not said hello yet. Reconnecting should fix this.")
            return False
        return True

    async def on_text(self, raw: str) -> None:
        """Routes one JSON message to its handler by type."""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            await self.error("bad_message", "The server got a message it could not read.")
            return
        from voice.calls.manager import CLIENT_TYPES

        if message.get("type") in CLIENT_TYPES:
            await self.runtime.calls.handle(self, message)
            return
        handler = getattr(self, f"on_{message.get('type', '')}", None)
        if handler is None or message.get("type") == "audio":
            await self.error("unknown_type", f"The server does not handle {message.get('type')!r} messages.")
            return
        await handler(message)


async def run_session(ws: WebSocket, runtime: Runtime) -> None:
    """Serves one app connection until it closes."""
    session = Session(ws, runtime)
    runtime.sessions.add(session)
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
    finally:
        runtime.sessions.discard(session)
        if session.call is not None:
            await runtime.calls.session_closed(session)
        for task in list(session.tasks):
            task.cancel()
