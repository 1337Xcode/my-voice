"""The call manager: rings his app for guest calls, places phone calls, and ends calls from either side.

His app sends the messages in CLIENT_TYPES over its normal session; guests and Twilio come in through routes.py.
"""

import asyncio
import logging

from pydantic import ValidationError

from voice.calls.call import Call
from voice.calls.codes import CallCodes
from voice.calls.twilio import TWILIO_STATUSES, PhoneError, PhoneLine, StreamStart, create_call

log = logging.getLogger("voice.calls.manager")

# The host (app) messages this module handles; the session routes them here.
CLIENT_TYPES = {"answer_call", "decline_call", "hangup_call"}
RING_TIMEOUT_S = 45


class CallManager:
    """Every live call in this container, by id (a single-user system, so a handful at most)."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.calls: dict[str, Call] = {}
        self.codes = CallCodes(runtime)

    def sessions_for(self, speaker: str) -> list:
        """His connected app sessions (a phone and a laptop may both be open)."""
        return [s for s in self.runtime.sessions if s.speaker == speaker]

    async def handle(self, session, message: dict) -> None:
        """One call message from his app: answer, decline or hang up."""
        call = self.calls.get(str(message.get("call_id")))
        if call is None:
            await session.error("unknown_call", "That call has already ended.")
            return
        kind = message.get("type")
        if kind == "answer_call":
            await self.answer(session, call)
        elif kind == "decline_call" and call.state == "ringing" and session in call.ringing:
            await self.finish(call, "ended", "Declined.", "They can't take the call right now.")
        elif kind == "hangup_call" and session in (call.host, *call.ringing):
            await self.finish(call, "ended", "Call ended.", "They hung up.")
        else:
            await session.error("call_not_ringing", "That call is no longer ringing.")

    async def ring(self, speaker: str, name: str, far) -> Call:
        """A guest dialled his code: rings every app he has open, or fails when he isn't reachable."""
        call = Call("app", name, far, self.runtime)
        sessions = self.sessions_for(speaker)
        if any(s.call is not None for s in sessions):
            await call.set_state("failed", far_detail="They're on another call right now.")
            return call
        if not sessions:
            await call.set_state("failed", far_detail="They're not available right now.")
            return call
        self.calls[call.id] = call
        await call.set_state("ringing")  # Only the guest hears "ringing"; his apps get incoming_call.
        call.ringing = set(sessions)
        for session in sessions:
            await session.send({"type": "incoming_call", "call_id": call.id, "name": name, "kind": "app"})
        call.spawn(self._ring_timeout(call))
        return call

    async def _ring_timeout(self, call: Call) -> None:
        await asyncio.sleep(RING_TIMEOUT_S)
        if call.state == "ringing":
            await self.finish(call, "failed", f"Missed call from {call.name}.", "No answer.")

    async def answer(self, session, call: Call) -> None:
        """He picked up on one device: the call connects there and stops ringing everywhere else."""
        if call.state != "ringing" or session not in call.ringing:
            await session.error("call_not_ringing", "That call is no longer ringing.")
            return
        if session.call is not None:
            await session.error("already_in_call", "Hang up the current call first.")
            return
        for other in call.ringing - {session}:
            await other.send(call.status_message("ended", "Answered on another device."))
        call.ringing = set()
        call.host, session.call = session, call
        await call.connect()

    async def start_phone_call(self, session, number: str, name: str, opening_line: str, base_url: str) -> Call:
        """Places a phone call for his session; raises PhoneError (after reporting it) when Twilio refuses."""
        line = PhoneLine(self.runtime.client(), opening_line)
        call = Call("phone", name or number, line, self.runtime)
        call.host, session.call = session, call
        self.calls[call.id] = call
        await call.set_state("dialling", f"Calling {call.name}.")
        try:
            line.call_sid = await create_call(self.runtime.client(), number, f"{base_url}/twilio/voice?call_id={call.id}",
                                              f"{base_url}/twilio/status?call_id={call.id}")
        except PhoneError as error:
            await self.finish(call, "failed", str(error), "", hang_up=False)
            raise
        return call

    async def phone_status(self, call_id: str, twilio_status: str) -> None:
        """A Twilio status callback: ringing, or the end of the call (answered is handled by the stream)."""
        call = self.calls.get(call_id)
        if call is None or call.kind != "phone" or twilio_status not in TWILIO_STATUSES:
            return
        state, detail = TWILIO_STATUSES[twilio_status]
        if state in ("ended", "failed"):
            await self.finish(call, state, detail, "", hang_up=False)
        elif call.state != "connected" and state != call.state:
            await call.set_state(state, detail)

    async def phone_answered(self, ws, event: dict) -> Call | None:
        """The media stream started: link it to its call, connect, and say his opening line."""
        try:
            start = StreamStart.model_validate(event)
        except ValidationError:
            log.warning("media stream start without the expected fields")
            return None
        call = self.calls.get(start.start.customParameters.get("call_id", ""))
        if call is None or call.kind != "phone" or not call.is_live():
            return None
        call.far.attach(ws, start.streamSid)
        await call.connect()
        if call.far.opening_line and call.host is not None:
            call.spawn(call.relay_sentence(call.host, call.far.opening_line))
        return call

    async def hang_up(self, call: Call) -> None:
        """He ended the call from the Hang up button's route."""
        await self.finish(call, "ended", "Call ended.", "They hung up.")

    async def finish(self, call: Call, state: str, host_detail: str, far_detail: str, hang_up: bool = True) -> None:
        """Ends a call once: stops its captions and work, tells both sides, and closes the far side."""
        if self.calls.pop(call.id, None) is None:
            return
        call.stop()
        await call.set_state(state, host_detail, far_detail)
        if call.host is not None and call.host.call is call:
            call.host.call = None
        await call.far.close(hang_up=hang_up)

    async def session_closed(self, session) -> None:
        """His app disconnected: a call it was on drops; a call only ringing there keeps ringing elsewhere."""
        for call in list(self.calls.values()):
            call.ringing.discard(session)
            if call.host is session:
                call.host = None
                await self.finish(call, "ended", "", "The call dropped.")
            elif call.state == "ringing" and call.kind == "app" and not call.ringing:
                await self.finish(call, "ended", "", "They're not available right now.")

    async def guest_left(self, call: Call) -> None:
        """The guest hung up or their connection closed."""
        await self.finish(call, "ended", f"{call.name} hung up.", "Call ended.", hang_up=False)
