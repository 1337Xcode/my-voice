"""Starts retraining from the server and relays its progress to the app (spec 9.3 triggers, 12.1 `training`)."""

import asyncio
import logging
import time

from voice.clips.records import load_clips
from voice.clips.selection import is_trainable
from voice.training.registry import write_status

log = logging.getLogger("voice.training.trigger")

JOBS_APP = "my-voice-jobs"
TRAIN_FUNCTION = "train_job"
RUNNING_STATES = ("queued", "training", "evaluating")
TERMINAL_STATES = ("promoted", "not_better", "failed")
POLL_EVERY_S = 3.0
POLL_FOR_S = 20 * 60
# Automatic retraining: enough new trainable clips, and he hasn't spoken for a while (spec 9.3).
AUTO_NEW_CLIPS = 20
AUTO_QUIET_S = 120
# A "running" status older than this is a crashed job, not a running one.
STALE_AFTER_S = 30 * 60


def read_status(runtime, speaker: str) -> dict:
    """The trainer's latest committed status, read without remounting the volume."""
    return runtime.committed_json("models", f"{speaker}/train_status.json", {"state": "idle", "message": "No training yet."})


def is_running(status: dict) -> bool:
    return status.get("state") in RUNNING_STATES and time.time() - status.get("updated_at", 0) < STALE_AFTER_S


async def start_training(runtime, speaker: str, reason: str) -> dict:
    """Spawns the train job unless one is already running, and starts relaying its status."""
    import modal

    status = await asyncio.to_thread(read_status, runtime, speaker)
    if is_running(status):
        return status
    status = await asyncio.to_thread(write_status, speaker, "queued", "Queued to improve your model.", reason=reason,
                                     started_at=round(time.time(), 3))
    runtime.commit_volumes()
    function = modal.Function.from_name(JOBS_APP, TRAIN_FUNCTION)
    await function.spawn.aio(speaker)
    runtime.background(relay_status(runtime, speaker))
    return status


async def relay_status(runtime, speaker: str) -> None:
    """Pushes each status change to the app until training ends."""
    last = None
    deadline = time.time() + POLL_FOR_S
    while time.time() < deadline:
        status = await asyncio.to_thread(read_status, runtime, speaker)
        key = (status.get("state"), status.get("progress"), status.get("message"))
        if key != last:
            last = key
            await runtime.broadcast({"type": "training", "state": status.get("state"), "progress": status.get("progress"),
                                     "eta_s": status.get("eta_s"), "message": status.get("message", "")})
        if status.get("state") in TERMINAL_STATES:
            if status.get("state") == "promoted":
                await asyncio.to_thread(runtime.refresh_models)
                version = await asyncio.to_thread(runtime.ensure_adapter, speaker)
                await runtime.broadcast({"type": "model_update", "model_version": version, "metrics": status.get("metrics", {})})
            return
        await asyncio.sleep(POLL_EVERY_S)


def new_trainable_since(speaker: str, since: float) -> int:
    """Trainable clips recorded or approved after `since`."""
    return sum(is_trainable(c) and (c.created_at or 0) > since for c in load_clips(speaker).values())


async def maybe_auto_train(runtime, speaker: str) -> None:
    """Starts retraining once 20 new trainable clips exist and no turn happened in the last 2 minutes."""
    if time.time() - runtime.last_turn_at < AUTO_QUIET_S:
        return
    status = await asyncio.to_thread(runtime.committed_json, "models", f"{speaker}/train_status.json", {})
    since = float(status.get("started_at") or status.get("updated_at") or 0)
    if not is_running(status) and await asyncio.to_thread(new_trainable_since, speaker, since) >= AUTO_NEW_CLIPS:
        await start_training(runtime, speaker, reason="auto")
