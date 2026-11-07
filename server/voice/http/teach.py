"""Routes for Teach: recordings, clip edits, the next prompt, Review, and retraining (spec 12.2)."""

import asyncio
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from voice.clips.records import load_clips, save_clip
from voice.http.auth import SPEAKER_PATTERN, require_token
from voice.teach import prompts, recording
from voice.training import trigger

router = APIRouter(dependencies=[Depends(require_token)])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class ClipEdit(BaseModel):
    """Fields of a clip he may change."""

    text: str | None = None
    ok: bool | None = None
    excluded: bool | None = None


class ReviewIn(BaseModel):
    """His verdict on one everyday turn."""

    action: Literal["approve", "reject", "edit"]
    text: str | None = None


@router.post("/clips")
async def upload_clip(request: Request, audio: UploadFile = File(...), text: str = Form(..., min_length=1), phrase_id: str | None = Form(None),
                      prompt_id: str | None = Form(None), split: Literal["train", "test"] = Form("train"),
                      condition: Literal["quiet", "noisy"] = Form("quiet"), speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Stores one Teach recording; a phrase recording becomes a template at once (no training needed)."""
    raw = await audio.read()
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="The recording was empty or too large. Record it again.")
    suffix = Path(audio.filename or "clip.wav").suffix or ".wav"
    try:
        record = await asyncio.to_thread(recording.store_upload, speaker, raw, suffix, text, phrase_id, prompt_id, split, condition)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    runtime = request.app.state.runtime
    if record.phrase_id and record.split == "train" and runtime.phrases is not None:
        runtime.phrases.reload(speaker)
    runtime.commit_volumes()
    trigger.maybe_auto_train(runtime, speaker)
    return {"clip": record.model_dump(), "progress": prompts.progress(speaker)}


@router.patch("/clips/{clip_id}")
async def edit_clip(clip_id: str, change: ClipEdit, request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    clips = await asyncio.to_thread(load_clips, speaker)
    if clip_id not in clips:
        raise HTTPException(status_code=404, detail="That clip doesn't exist.")
    clip = clips[clip_id].model_copy(update=change.model_dump(exclude_none=True))
    await asyncio.to_thread(save_clip, clip)
    request.app.state.runtime.commit_volumes()
    return {"clip": clip.model_dump()}


@router.get("/clips/{clip_id}/audio")
async def clip_audio(clip_id: str, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    path = recording.clip_audio_file(speaker, clip_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="That recording isn't stored.")
    return FileResponse(path, media_type="audio/wav")


@router.get("/teach/next")
async def teach_next(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    prompt = await asyncio.to_thread(prompts.next_prompt, speaker)
    return {"prompt": prompt, "progress": await asyncio.to_thread(prompts.progress, speaker)}


@router.get("/teach/test-sentences")
async def test_sentences(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Onboarding step 4: Harvard list 1 as ta01..ta10."""
    return {"sentences": await asyncio.to_thread(prompts.test_sentences, speaker)}


@router.post("/teach/freeze")
async def freeze(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Freezes his test set and builds its babble versions (after the onboarding test sentences)."""
    from voice.training.improve import refreeze_test_set

    frozen = await asyncio.to_thread(refreeze_test_set, speaker)
    request.app.state.runtime.commit_volumes()
    return {"test_set": frozen.as_dict()}


@router.get("/review")
async def review(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    return {"items": await asyncio.to_thread(recording.review_items, speaker)}


@router.post("/review/{turn_id}")
async def review_one(turn_id: str, verdict: ReviewIn, request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    try:
        clip = await asyncio.to_thread(recording.apply_review, speaker, turn_id, verdict.action, verdict.text)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="That turn is no longer waiting for review.") from error
    runtime = request.app.state.runtime
    runtime.commit_volumes()
    trigger.maybe_auto_train(runtime, speaker)
    return {"clip": clip.model_dump()}


@router.post("/train")
async def train(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Improve now: starts retraining on Modal and streams its status to the app."""
    return await trigger.start_training(request.app.state.runtime, speaker, reason="improve_now")


@router.get("/train/status")
async def train_status(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    return await asyncio.to_thread(trigger.read_status, request.app.state.runtime, speaker)
