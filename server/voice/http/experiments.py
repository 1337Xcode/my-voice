"""Routes for the Experiments screen (EXP-SPEC): which experiments are on, and their measured numbers."""

import asyncio
import time

from fastapi import APIRouter, Depends, Query, Request

from voice.config import features
from voice.http.auth import SPEAKER_PATTERN, require_token
from voice.lips.report import CaptureReport, capture_verdict
from voice.lips.store import load_lips
from voice.realtime.report import realtime_report
from voice.storage import append_jsonl, read_jsonl, speaker_dir
from voice.turns.record import load_turns

router = APIRouter(dependencies=[Depends(require_token)])


def _capture_log(speaker: str):
    return speaker_dir(speaker) / "lips_capture.jsonl"


def lips_report(speaker: str, turns: list[dict]) -> dict:
    """The latest capture test, the stored sync offsets, and capture quality over his lips turns."""
    tests = list(read_jsonl(_capture_log(speaker))) if _capture_log(speaker).exists() else []
    devices = load_lips(speaker).get("devices", {})
    lip_turns = [t["exp"]["lips"] for t in turns if (t.get("exp") or {}).get("lips")][-50:]
    return {
        "capture": capture_verdict(tests[-1]) if tests else None,
        "sync_offsets_ms": [d["offset_ms"] for d in devices.values()],
        "turns": len(lip_turns),
        "turn_face_visible_pct": round(sum(t["face_visible_pct"] for t in lip_turns) / len(lip_turns), 1) if lip_turns else None,
    }


@router.get("/experiments/report")
async def experiments_report(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """The server's experiment flags and the numbers each acceptance check is judged on."""
    flags = features()
    turns = await asyncio.to_thread(load_turns, speaker)
    lips = await asyncio.to_thread(lips_report, speaker, turns)
    return {"realtime_voice": flags.realtime_voice, "lips": flags.lips, "realtime": realtime_report(turns), "lips_report": lips}


@router.post("/lips/capture_report")
async def save_capture_report(report: CaptureReport, request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Keeps one capture test's measurements (X0) and returns its verdict."""
    record = {**report.model_dump(), "at": int(time.time())}
    await asyncio.to_thread(append_jsonl, _capture_log(speaker), record)
    request.app.state.runtime.commit_volumes()
    return capture_verdict(record)
