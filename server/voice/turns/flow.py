"""The turn flow for one session: recognise, decide, speak, and record each step's time (spec 8)."""

import asyncio
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

from voice.phrases.bank import load_bank, save_bank
from voice.turns.turn import Candidate, Turn

if TYPE_CHECKING:
    from voice.session import Session

log = logging.getLogger("voice.flow")

RECENT_TURNS = 20
CONVERSATION_TURNS = 6
PICK_OPTIONS = 3


class TurnFlow:
    """Runs each turn of one session from end of speech to its outcome."""

    def __init__(self, session: "Session"):
        self.session = session
        self.recent: OrderedDict[str, Turn] = OrderedDict()
        self.conversation: list[dict] = []

    @property
    def runtime(self):
        return self.session.runtime

    def remember(self, turn: Turn) -> None:
        """Keeps the last few turns so a late choose, confirm or client_timing can find them."""
        self.recent[turn.id] = turn
        while len(self.recent) > RECENT_TURNS:
            self.recent.popitem(last=False)

    async def process(self, turn: Turn) -> None:
        """End of speech → recognisers → decision → result (and voice when speaking)."""
        self.remember(turn)
        if turn.audio.too_short():
            await self.ignore(turn, "too_short" if turn.audio.state.speech_ms > 0 else "no_speech")
            return
        speaker = self.session.speaker
        turn.record.model_version = await asyncio.to_thread(self.runtime.ensure_adapter, speaker)
        recognition = await asyncio.to_thread(self.runtime.whisper.nbest, turn.audio.speech_audio())
        turn.record.mark("t_asr")
        turn.nbest = recognition.hypotheses
        turn.record.asr = {"ms": round(recognition.ms, 1), "no_speech": recognition.no_speech_probability, "dropped": recognition.dropped,
                           "nbest": [{"text": h.text, "logprob": h.logprob} for h in recognition.hypotheses]}
        if not recognition.hypotheses:
            await self.ignore(turn, "no_speech")
            return
        await self.decide(turn)

    async def decide(self, turn: Turn) -> None:
        """Stand-in decision until the gate lands: always offer the top hypotheses to pick from."""
        turn.candidates = [Candidate(id=f"c{i + 1}", text=h.text, p=0.0, sources=["asr"]) for i, h in enumerate(turn.nbest[:PICK_OPTIONS])]
        await self.send_result(turn, "pick", chosen_id=None)

    async def send_result(self, turn: Turn, action: str, chosen_id: str | None) -> None:
        """Sends the decision; for `speak`, the voice starts in parallel with the message."""
        turn.action = action
        turn.state = "decided"
        turn.record.action = action
        turn.record.candidates = [c.as_message() for c in turn.candidates]
        speaking = None
        if action == "speak" and chosen_id:
            speaking = asyncio.create_task(self.speak_turn(turn, turn.candidate(chosen_id).text, outcome="spoken"))
        turn.record.mark("t_result_sent")
        await self.session.send({"type": "result", "turn_id": turn.id, "action": action, "candidates": turn.record.candidates,
                                 "chosen_id": chosen_id, "timings": turn.record.stage_ms()})
        await asyncio.to_thread(turn.record.save)
        if speaking:
            await speaking

    async def ignore(self, turn: Turn, reason: str) -> None:
        """Nothing to say for this turn."""
        turn.state = "finished"
        turn.record.action = "ignored"
        turn.record.outcome = reason
        await self.session.send({"type": "ignored", "turn_id": turn.id, "reason": reason})
        await asyncio.to_thread(turn.record.save)

    async def speak_turn(self, turn: Turn, text: str, outcome: str) -> None:
        """Speaks a turn's final sentence and records it."""
        ok = await self.session.speak(text, turn_id=turn.id, record=turn.record)
        turn.state = "finished"
        turn.record.final_text = text
        turn.record.outcome = outcome if ok else "voice_failed"
        if ok:
            self.add_to_conversation("me", text)
        await asyncio.to_thread(turn.record.save)

    def add_to_conversation(self, who: str, text: str) -> None:
        """Keeps the last few sentences (his and partners') as context for the gate."""
        self.conversation.append({"who": who, "text": text})
        del self.conversation[:-CONVERSATION_TURNS]

    async def choose(self, turn_id: str | None, candidate_id: str | None, text: str | None, via: str) -> None:
        """His explicit choice: speak it (spec 9.1)."""
        turn = self.recent.get(str(turn_id))
        candidate = turn.candidate(candidate_id) if turn and candidate_id else None
        sentence = (candidate.text if candidate else (text or "")).strip()
        if not sentence:
            await self.session.error("bad_choice", "That option is no longer available. Say it again or type it.")
            return
        if turn is None:
            await self.session.speak(sentence, turn_id=turn_id)
            return
        await self.speak_turn(turn, sentence, outcome="typed" if via == "typed" else "picked")

    async def confirm(self, turn_id: str | None) -> None:
        """Check-first: he confirmed the top candidate."""
        turn = self.recent.get(str(turn_id))
        if turn is None or not turn.candidates:
            await self.session.error("bad_confirm", "That sentence is no longer available. Say it again or type it.")
            return
        await self.speak_turn(turn, turn.candidates[0].text, outcome="confirmed")

    async def reject(self, turn_id: str | None) -> None:
        """'Not what I meant': record it and offer the other candidates."""
        turn = self.recent.get(str(turn_id))
        if turn is None:
            return
        spoken = (turn.record.final_text or "").strip().lower()
        turn.candidates = [c for c in turn.candidates if c.text.strip().lower() != spoken]
        turn.record.outcome = "rejected"
        await self.send_result(turn, "pick", chosen_id=None)

    async def say_phrase(self, phrase_id: str) -> None:
        """Speaks a bank phrase and counts the use."""
        speaker = self.session.speaker
        bank = await asyncio.to_thread(load_bank, speaker)
        phrase = next((p for p in bank if p.id == phrase_id), None)
        if phrase is None:
            await self.session.error("unknown_phrase", "That phrase is no longer in your bank.")
            return
        if await self.session.speak(phrase.text, phrase_id=phrase_id):
            phrase.uses += 1
            self.add_to_conversation("me", phrase.text)
            await asyncio.to_thread(save_bank, speaker, bank)

    async def client_timing(self, message: dict) -> None:
        """Stores the app's measured times on the turn's record."""
        turn = self.recent.get(str(message.get("turn_id")))
        if turn is None:
            return
        for key in ("ms_end_to_text", "ms_end_to_audio"):
            if isinstance(message.get(key), (int, float)):
                setattr(turn.record, key, int(message[key]))
        await asyncio.to_thread(turn.record.save)
        log.info("turn %s timings %s text=%s audio=%s", turn.id, turn.record.stage_ms(), turn.record.ms_end_to_text, turn.record.ms_end_to_audio)

