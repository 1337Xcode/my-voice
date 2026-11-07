"""The turn flow for one session: recognise, decide, speak, and record each step's time."""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from voice.gate.act import GateSettings
from voice.gate.candidates import Hypothesis as GateHypothesis
from voice.gate.candidates import PhraseMatch as GatePhraseMatch
from voice.gate.pipeline import learn_from_choice, run_gate
from voice.config import MissingKey
from voice.gate.candidates import normalise
from voice.gate.decide import DecisionError
from voice.tell.mapping import map_request
from voice.phrases.bank import load_bank, save_bank
from voice.teach.recording import add_phrase_template, keep_turn_audio
from voice.turns.record import now_ms
from voice.turns.turn import Candidate, Turn

if TYPE_CHECKING:
    from voice.session import Session

log = logging.getLogger("voice.flow")

RECENT_TURNS = 20
CONVERSATION_TURNS = 6


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
        lips = self.session.lips
        if turn.mode == "lips_sync":
            turn.state = "finished"
            if lips is not None:
                await lips.sync_check(turn)
            await asyncio.to_thread(turn.record.save)
            return
        if lips is not None:
            turn.record.exp["lips"] = lips.summary(turn)
        if turn.mode == "them" or (turn.mode == "handsfree" and not await self.is_him(turn)):
            await self.caption_partner(turn)
            return
        self.runtime.last_turn_at = time.time()
        await self.session.peer_state("thinking")
        if turn.audio.too_short():
            await self.ignore(turn, "too_short" if turn.audio.state.speech_ms > 0 else "no_speech")
            return
        speaker = self.session.speaker
        turn.record.model_version = await asyncio.to_thread(self.runtime.ensure_adapter, speaker)
        recognition, phrase_result = await self.recognise(turn)
        turn.record.mark("t_asr")
        turn.phrase_matches = phrase_result.matches if phrase_result else []
        turn.nbest = recognition.hypotheses
        turn.record.asr = {"ms": round(recognition.ms, 1), "no_speech": recognition.no_speech_probability, "dropped": recognition.dropped,
                           "nbest": [{"text": h.text, "logprob": h.logprob, "support": h.support} for h in recognition.hypotheses]}
        if not recognition.hypotheses and not turn.phrase_matches:
            await self.ignore(turn, "no_speech")
            return
        if turn.mode == "tell":
            await self.propose_settings(turn)
            return
        await self.decide(turn)

    async def propose_settings(self, turn: Turn) -> None:
        """'Tell the app': maps his request to an allowed change and asks him to confirm it."""
        heard = [h.text for h in turn.nbest]
        try:
            mapped = await map_request(self.runtime.client(), heard)
        except (DecisionError, MissingKey) as error:
            turn.record.errors.append(f"tell: {error}")
            await self.session.error("tell_failed", "I couldn't work out that request just now. Try again, or change it in Settings.")
            return
        turn.state = "finished"
        turn.record.action, turn.record.outcome = "tell", "proposed" if mapped["changes"] else "not_understood"
        turn.record.gate = {"tell": mapped}
        turn.record.mark("t_result_sent")
        await self.session.send({"type": "settings_proposal", "turn_id": turn.id, "changes": mapped["changes"], "heard": heard[0] if heard else ""})
        await self.session.peer_state("idle")
        await asyncio.to_thread(turn.record.save)

    async def is_him(self, turn: Turn) -> bool:
        """Hands-free: the speaker gate decides whether this segment is his."""
        gate = self.runtime.speaker_gate
        if gate is None or turn.audio.too_short():
            return True
        mine, score = await asyncio.to_thread(gate.is_him, self.session.speaker, turn.audio.speech_audio())
        turn.record.gate["speaker_score"] = score
        return mine

    async def caption_partner(self, turn: Turn) -> None:
        """'Them': the other person's speech becomes a caption with the stock model; never spoken, never stored."""
        turn.state = "finished"
        if turn.audio.too_short():
            await self.session.send({"type": "ignored", "turn_id": turn.id, "reason": "no_speech"})
            return
        text = await asyncio.to_thread(self.runtime.whisper.transcribe, turn.audio.speech_audio(), True)
        if text:
            self.add_to_conversation("them", text)
            await self.session.send({"type": "partner_caption", "text": text, "source": "room", "turn_id": turn.id})
        else:
            await self.session.send({"type": "ignored", "turn_id": turn.id, "reason": "no_speech"})

    def partial(self, turn: Turn) -> None:
        """A quick greedy decode of the audio so far, sent as `partial`; skipped while the previous one runs."""
        if turn.partial_task is not None and not turn.partial_task.done():
            return

        async def run() -> None:
            text = await asyncio.to_thread(self.runtime.whisper.greedy, turn.audio.audio())
            if text and turn.state == "listening":
                await self.session.send({"type": "partial", "turn_id": turn.id, "text": text})

        turn.partial_task = asyncio.create_task(run())

    def speculate(self, turn: Turn) -> None:
        """He paused: start recognising now, so the result is ready if this turns out to be the end."""
        if turn.speculation is not None and not turn.speculation["task"].done():
            return  # one speculative decode at a time
        end = turn.audio.state.last_speech_sample
        task = asyncio.create_task(self.run_recognisers(turn, turn.audio.speech_audio()))
        turn.speculation = {"end": end, "task": task}

    async def recognise(self, turn: Turn):
        """Reuses the speculative result when no speech arrived after it started; otherwise recognises the whole turn."""
        speculation = turn.speculation
        if speculation is not None and speculation["end"] == turn.audio.state.last_speech_sample:
            turn.record.asr["speculative"] = True
            return await speculation["task"]
        if speculation is not None:
            speculation["task"].cancel()
        return await self.run_recognisers(turn, turn.audio.speech_audio())

    async def run_recognisers(self, turn: Turn, audio):
        """Steps: the personal recogniser and the phrase matcher run at the same time on the GPU."""
        return await asyncio.gather(asyncio.to_thread(self.runtime.whisper.nbest, audio), self.match_phrases(turn, audio))

    async def match_phrases(self, turn: Turn, audio):
        """Matches the utterance against his recorded phrases; a failure here never stops the turn."""
        if self.runtime.phrases is None:
            return None
        try:
            result = await asyncio.to_thread(self.runtime.phrases.match, self.session.speaker, audio)
        except Exception as error:  # the matcher is a secondary recogniser: log it and carry on with ASR
            log.exception("phrase matcher failed")
            turn.record.errors.append(f"phrase: {error}")
            return None
        turn.record.mark("t_phrase")
        if result is not None:
            turn.record.asr["phrases"] = {"rejected": result.rejected, "best": result.best_distance, "ms": round(result.ms, 1),
                                          "matches": [{"id": m.phrase_id, "d": round(m.distance, 3), "score": round(m.score, 3)} for m in result.matches]}
        return result

    async def decide(self, turn: Turn) -> None:
        """Runs the gate and acts on it: speak, pick or again."""
        settings = self.session.settings()
        gate_settings = GateSettings(float(settings["speak_threshold"]), float(settings["pick_threshold"]), settings["before_speaking"] == "check")
        nbest = [GateHypothesis(h.text, h.logprob, h.support) for h in turn.nbest]
        phrases = [GatePhraseMatch(m.phrase_id, m.text, m.distance, m.score, m.margin) for m in turn.phrase_matches]
        started_ms = now_ms()
        gate = await run_gate(self.session.speaker, nbest, phrases, [c["text"] for c in self.conversation], gate_settings,
                              settings["decide_provider"], self.runtime.client())
        for stage, offset in gate.timings.items():
            if offset is not None:
                setattr(turn.record, stage, started_ms + offset)
        turn.record.gate = {"provider": gate.provider, "model": gate.model, "errors": gate.errors, "shown": gate.shown_ids}
        turn.record.errors.extend(f"{step}: {message}" for step, message in gate.errors.items())
        by_id = {c.id: c for c in gate.candidates}
        shown = [by_id[i] for i in gate.shown_ids if i in by_id] or gate.candidates[:1]
        turn.candidates = [Candidate(id=c.id, text=c.text, p=c.p or 0.0, sources=c.sources) for c in shown]
        turn.all_candidates = [Candidate(id=c.id, text=c.text, p=c.p or 0.0, sources=c.sources) for c in gate.candidates]
        await self.send_result(turn, gate.action, chosen_id=gate.chosen_id)

    async def send_result(self, turn: Turn, action: str, chosen_id: str | None) -> None:
        """Sends the decision; for `speak`, the voice starts in parallel with the message."""
        turn.action = action
        turn.state = "decided"
        turn.record.action = action
        turn.record.candidates = [c.as_message() for c in turn.candidates]
        speaking = None
        if action == "speak" and chosen_id:
            speaking = asyncio.create_task(self.speak_turn(turn, turn.candidate(chosen_id).text, outcome="spoken"))
        if action != "speak":
            await self.session.peer_state("choosing")
        turn.record.mark("t_result_sent")
        await self.session.send({"type": "result", "turn_id": turn.id, "action": action, "candidates": turn.record.candidates,
                                 "chosen_id": chosen_id, "timings": turn.record.stage_ms()})
        await asyncio.to_thread(turn.record.save)
        if speaking:
            await speaking

    async def ignore(self, turn: Turn, reason: str) -> None:
        """Nothing to say for this turn."""
        turn.state = "finished"
        await self.session.peer_state("idle")
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
        if ok and outcome == "spoken":
            # An unchallenged spoken sentence counts toward its frequency.
            await self.learn(turn, text, "spoken")
        if ok and self.session.settings().get("learn_from_conversations"):
            await self.keep_audio(turn, text, trust="implicit" if outcome == "spoken" else "explicit")

    async def keep_audio(self, turn: Turn, text: str, trust: str) -> None:
        """With "Learn from my conversations" on: keep the turn as a clip, and as a phrase template if it's a bank phrase."""
        speaker = self.session.speaker
        bank = await asyncio.to_thread(load_bank, speaker)
        phrase = next((p for p in bank if normalise(p.text) == normalise(text)), None)
        record = await asyncio.to_thread(keep_turn_audio, speaker, turn.id, turn.audio.speech_audio(), text, trust, phrase.id if phrase else None)
        turn.record.audio_kept = True
        if phrase and trust == "explicit":
            await asyncio.to_thread(add_phrase_template, speaker, phrase.id, record.id)
            if self.runtime.phrases is not None:
                self.runtime.phrases.reload(speaker)
            await self.session.send({"type": "learned", "turn_id": turn.id, "kind": "template"})
        self.runtime.commit_volumes()

    def add_to_conversation(self, who: str, text: str) -> None:
        """Keeps the last few sentences (his and partners') as context for the gate."""
        self.conversation.append({"who": who, "text": text})
        del self.conversation[:-CONVERSATION_TURNS]

    async def choose(self, turn_id: str | None, candidate_id: str | None, text: str | None, via: str) -> None:
        """His explicit choice: speak it."""
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
        await self.learn(turn, sentence, "typed" if via == "typed" else "pick")

    async def confirm(self, turn_id: str | None) -> None:
        """Check-first: he confirmed the top candidate."""
        turn = self.recent.get(str(turn_id))
        if turn is None or not turn.candidates:
            await self.session.error("bad_confirm", "That sentence is no longer available. Say it again or type it.")
            return
        await self.speak_turn(turn, turn.candidates[0].text, outcome="confirmed")
        await self.learn(turn, turn.candidates[0].text, "pick")

    async def reject(self, turn_id: str | None) -> None:
        """'Not what I meant': record it and offer the other candidates."""
        turn = self.recent.get(str(turn_id))
        if turn is None:
            return
        spoken = (turn.record.final_text or "").strip().lower()
        turn.candidates = [c for c in (turn.all_candidates or turn.candidates) if c.text.strip().lower() != spoken][:3]
        turn.record.outcome = "rejected"
        await self.send_result(turn, "pick", chosen_id=None)

    async def learn(self, turn: Turn, meant: str, source: str) -> None:
        """Adds what he meant to the correction memory and shows the Learned note for corrections."""
        if not turn.nbest:
            return
        heard = turn.nbest[0].text
        await asyncio.to_thread(learn_from_choice, self.session.speaker, heard, [h.text for h in turn.nbest], meant, source)
        self.runtime.commit_volumes()
        if source in ("pick", "typed") and meant.strip().lower() != heard.strip().lower():
            await self.session.send({"type": "learned", "turn_id": turn.id, "kind": "memory"})

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

