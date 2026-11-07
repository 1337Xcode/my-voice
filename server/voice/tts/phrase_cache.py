"""Pre-synthesises every bank phrase in his voice so phrases play instantly, offline too (spec 8.9)."""

import asyncio
import logging

from voice.phrases.bank import load_bank, save_bank
from voice.storage import speaker_dir
from voice.tts.elevenlabs import APP_FORMAT, VoiceError, cache_path, synthesise

log = logging.getLogger("voice.phrase_cache")

# Parallel ElevenLabs requests while filling the cache; small to stay inside plan concurrency limits.
CONCURRENCY = 3


def tts_key(voice_id: str, fmt: str = APP_FORMAT) -> str:
    """The key a phrase's `tts` map uses for one voice and format."""
    return f"{voice_id}:{fmt}"


async def presynthesise(client, speaker: str, voice_id: str, speed: float = 1.0) -> dict:
    """Fills the cache for every phrase and records each file in the bank; returns counts."""
    bank = await asyncio.to_thread(load_bank, speaker)
    limit = asyncio.Semaphore(CONCURRENCY)
    failures: list[str] = []
    files: dict[str, str] = {}

    async def one(phrase) -> None:
        async with limit:
            try:
                await synthesise(client, speaker, phrase.text, voice_id, APP_FORMAT, speed)
            except VoiceError as error:
                failures.append(f"{phrase.id}: {error}")
                return
        path = cache_path(speaker, voice_id, APP_FORMAT, f"{speed:.2f}|{phrase.text}")
        files[phrase.id] = str(path.relative_to(speaker_dir(speaker) / "tts")).replace("\\", "/")

    await asyncio.gather(*(one(phrase) for phrase in bank))
    # Re-read the bank so an edit made while synthesising is kept.
    latest = await asyncio.to_thread(load_bank, speaker)
    for phrase in latest:
        if phrase.id in files:
            phrase.tts[tts_key(voice_id)] = files[phrase.id]
    await asyncio.to_thread(save_bank, speaker, latest)
    if failures:
        log.warning("phrase cache failures: %s", failures[:5])
    return {"phrases": len(bank), "failed": len(failures), "errors": failures[:5]}
