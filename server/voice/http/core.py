"""Core routes: liveness, wake, state, pipeline settings and the trainer's reload call."""

import asyncio
import time

from fastapi import APIRouter, Depends, Query, Request

from voice.config import SERVER_VERSION, SPEAKERS, features
from voice.http.auth import SPEAKER_PATTERN, require_internal_token, require_token
from voice.http.settings_model import SettingsIn, valid_settings
from voice.storage import latest_by_id, speaker_dir
from voice.tts.elevenlabs import voices
from voice.tts.phrase_cache import presynthesise

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    runtime = request.app.state.runtime
    return {"ok": True, "version": SERVER_VERSION, "model_loaded": runtime.whisper is not None, "uptime_s": round(time.time() - runtime.loaded_at, 1)}


@router.post("/wake", dependencies=[Depends(require_token)])
async def wake(request: Request):
    return {"ok": True, "warm": True, "load_s": request.app.state.runtime.load_seconds}


@router.get("/state", dependencies=[Depends(require_token)])
async def state(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Active model, registry summary, clip counts, Review count, settings and features."""
    runtime = request.app.state.runtime
    clips = [c for c in latest_by_id(speaker_dir(speaker) / "clips.jsonl").values() if not c.get("excluded")]
    return {
        "speaker": speaker,
        "model_version": runtime.model_version(speaker),
        "registry": await asyncio.to_thread(runtime.committed_json, "models", f"{speaker}/registry.json", {}),
        "clips": {"total": len(clips), "train": sum(c.get("split") == "train" for c in clips), "test": sum(c.get("split") == "test" for c in clips)},
        "review_count": sum(c.get("trust") == "implicit" for c in clips),
        "settings": runtime.settings(speaker),
        "features": features().as_dict(),
        "speakers": list(SPEAKERS),
    }


@router.post("/settings", dependencies=[Depends(require_token)])
async def save_settings(request: Request, change: SettingsIn, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Saves pipeline settings; a new voice re-fills the phrase audio cache in the background."""
    runtime = request.app.state.runtime
    values = valid_settings(change.model_dump(exclude_none=True))
    before = runtime.settings(speaker)
    merged = await asyncio.to_thread(runtime.save_settings, speaker, values)
    if merged["voice_id"] != before["voice_id"] or merged["speech_rate"] != before["speech_rate"]:
        runtime.background(presynthesise(runtime.client(), speaker, merged["voice_id"] or voices()["default"], float(merged["speech_rate"])))
    return {"settings": merged}


@router.post("/internal/reload", dependencies=[Depends(require_internal_token)])
async def reload(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """After a promotion: re-read the volumes; the next turn swaps to the new adapter."""
    runtime = request.app.state.runtime
    await asyncio.to_thread(runtime.refresh_models)
    version = await asyncio.to_thread(runtime.ensure_adapter, speaker)
    await runtime.broadcast({"type": "model_update", "model_version": version, "metrics": runtime.registry(speaker).get("versions", {}).get(version, {}).get("metrics", {})})
    return {"ok": True, "model_version": version}
