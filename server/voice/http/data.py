"""His data (spec 11.7, 16): export everything as a zip, or delete everything, models included."""

import asyncio
import io
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from voice.http.auth import SPEAKER_PATTERN, require_token
from voice.storage import models_dir, speaker_dir

router = APIRouter(dependencies=[Depends(require_token)])


class DeleteConfirm(BaseModel):
    """He typed DELETE to confirm."""

    confirm: str


def zip_speaker(speaker: str) -> bytes:
    """Every file of his on both volumes, in one zip (data/ and models/)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for prefix, root in (("data", speaker_dir(speaker)), ("models", models_dir(speaker))):
            for path in sorted(Path(root).rglob("*")) if Path(root).exists() else []:
                if path.is_file():
                    archive.write(path, f"{prefix}/{path.relative_to(root).as_posix()}")
    return buffer.getvalue()


def delete_speaker(speaker: str) -> list[str]:
    """Removes his data and models folders; returns what was removed."""
    removed = []
    for root in (speaker_dir(speaker), models_dir(speaker)):
        if Path(root).exists():
            shutil.rmtree(root)
            removed.append(str(root))
    return removed


@router.get("/export")
async def export(speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    data = await asyncio.to_thread(zip_speaker, speaker)
    headers = {"Content-Disposition": f'attachment; filename="my-voice-{speaker}.zip"'}
    return StreamingResponse(iter([data]), media_type="application/zip", headers=headers)


@router.delete("/data")
async def delete_everything(body: DeleteConfirm, request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    if body.confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm.")
    runtime = request.app.state.runtime
    removed = await asyncio.to_thread(delete_speaker, speaker)
    runtime.commit_volumes()
    if runtime.phrases is not None:
        runtime.phrases.reload(speaker)
    await asyncio.to_thread(runtime.ensure_adapter, speaker)
    return {"deleted": True, "removed": len(removed)}
