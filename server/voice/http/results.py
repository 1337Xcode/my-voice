"""Routes for the Results screen and re-running evaluation (spec 12.2, 15.3)."""

import asyncio

import modal
from fastapi import APIRouter, Depends, Query, Request

from voice.evaluation.results import results
from voice.http.auth import SPEAKER_PATTERN, require_token
from voice.training.trigger import JOBS_APP

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/results")
async def get_results(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Words understood per system, learning over versions, live use and the calibrated threshold."""
    runtime = request.app.state.runtime
    await asyncio.to_thread(runtime.reload_volumes)
    return await asyncio.to_thread(results, speaker, runtime.registry(speaker))


@router.post("/eval/run")
async def run_evaluation(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Re-scores every registered version, then recalibrates the gate; both run on Modal in the background."""
    asr = await modal.Function.from_name(JOBS_APP, "eval_asr_job").spawn.aio(speaker)
    pipeline = await modal.Function.from_name(JOBS_APP, "eval_pipeline_job").spawn.aio(speaker, ["jev", "openai"])
    return {"started": True, "jobs": [asr.object_id, pipeline.object_id]}
