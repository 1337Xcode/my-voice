"""Routes for the phrase bank, the voice list and cached phrase audio (spec 12.2)."""

import asyncio
import base64
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from voice.http.auth import SPEAKER_PATTERN, require_token
from voice.phrases.bank import MAX_TEMPLATES, Phrase, load_bank, save_bank
from voice.storage import speaker_dir
from voice.tts.elevenlabs import APP_FORMAT, VoiceError, synthesise, voices
from voice.tts.phrase_cache import presynthesise

router = APIRouter(dependencies=[Depends(require_token)])

SAMPLE_SENTENCE = "Hello, this is the voice I'll use to speak for you."


class PhraseIn(BaseModel):
    """A phrase as the app sends it in PUT /phrases."""

    id: str
    text: str
    category: str = "Mine"
    order: int = 0
    pinned: bool = False


def runtime_of(request: Request):
    return request.app.state.runtime


def voice_for(runtime, speaker: str) -> str:
    return runtime.settings(speaker).get("voice_id") or voices()["default"]


@router.get("/phrases")
async def get_phrases(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    bank = await asyncio.to_thread(load_bank, speaker)
    return {"phrases": [phrase.model_dump() for phrase in bank]}


@router.put("/phrases")
async def put_phrases(request: Request, phrases: list[PhraseIn], speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Replaces the bank (keeping templates, cached audio and use counts), then refreshes the voice cache."""
    current = {phrase.id: phrase for phrase in await asyncio.to_thread(load_bank, speaker)}
    updated = []
    for incoming in phrases:
        kept = current.get(incoming.id)
        text_changed = kept is not None and kept.text != incoming.text
        updated.append(Phrase(**incoming.model_dump(), template_clip_ids=[] if text_changed or not kept else kept.template_clip_ids[-MAX_TEMPLATES:],
                              tts={} if text_changed or not kept else kept.tts, uses=kept.uses if kept else 0))
    await asyncio.to_thread(save_bank, speaker, updated)
    runtime = runtime_of(request)
    runtime.background(presynthesise(runtime.client(), speaker, voice_for(runtime, speaker), float(runtime.settings(speaker)["speech_rate"])))
    return {"phrases": [phrase.model_dump() for phrase in updated]}


@router.post("/phrases/cache")
async def refresh_cache(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Synthesises every phrase now and reports how many succeeded."""
    runtime = runtime_of(request)
    result = await presynthesise(runtime.client(), speaker, voice_for(runtime, speaker), float(runtime.settings(speaker)["speech_rate"]))
    runtime.commit_volumes()
    return result


@router.get("/tts/{file:path}")
async def tts_file(file: str, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Downloads one cached phrase clip for offline use."""
    root = (speaker_dir(speaker) / "tts").resolve()
    path = (root / file).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="That audio isn't cached. Refresh your phrases.")
    return FileResponse(Path(path), media_type="audio/mpeg")


@router.get("/voices")
async def list_voices():
    return voices()


@router.get("/voices/{voice_id}/sample")
async def voice_sample(request: Request, voice_id: str, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """A short sample sentence in one voice, as base64 mp3."""
    if voice_id not in {voice["id"] for voice in voices()["voices"]}:
        raise HTTPException(status_code=404, detail="That voice isn't in the list.")
    try:
        speech = await synthesise(runtime_of(request).client(), speaker, SAMPLE_SENTENCE, voice_id, APP_FORMAT)
    except VoiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"format": APP_FORMAT, "data": base64.b64encode(speech.audio).decode("ascii")}
