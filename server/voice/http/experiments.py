"""Routes for the Experiments screen (EXP-SPEC): which experiments are on, and their measured numbers."""

import asyncio

from fastapi import APIRouter, Depends, Query

from voice.config import features
from voice.http.auth import SPEAKER_PATTERN, require_token
from voice.realtime.report import realtime_report
from voice.turns.record import load_turns

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/experiments/report")
async def experiments_report(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """The server's experiment flags and the numbers each acceptance check is judged on."""
    flags = features()
    turns = await asyncio.to_thread(load_turns, speaker)
    return {"realtime_voice": flags.realtime_voice, "lips": flags.lips, "realtime": realtime_report(turns)}
