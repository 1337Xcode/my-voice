"""The FastAPI app the speech server exposes: HTTP routes and the app's WebSocket."""

import hmac
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from voice.config import SERVER_VERSION, SPEAKERS, MissingKey, features, require
from voice.phrases.bank import load_bank
from voice.runtime import Runtime
from voice.session import run_session
from voice.storage import latest_by_id, read_json, speaker_dir


def token_matches(given: str | None) -> bool:
    """True when the given bearer token equals APP_TOKEN, compared in constant time."""
    expected = require("APP_TOKEN", "the app connection")
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def bearer(authorization: str | None) -> str | None:
    """The token from an 'Authorization: Bearer <token>' header, if present."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_token(authorization: str | None = Header(default=None), token: str | None = Query(default=None)) -> None:
    """Route dependency: rejects requests without the app's bearer token."""
    if not token_matches(bearer(authorization) or token):
        raise HTTPException(status_code=401, detail="The app token is missing or wrong.")


def create_app(runtime: Runtime) -> FastAPI:
    """Builds the web app around the container's loaded runtime."""
    app = FastAPI(title="My Voice speech server", version=SERVER_VERSION)
    # Every route needs the bearer token, so any origin may call it (the web build uses this).
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(MissingKey)
    async def missing_key(_, error: MissingKey):
        return JSONResponse(status_code=503, content={"detail": str(error), "missing": error.variable})

    @app.get("/health")
    async def health():
        return {"ok": True, "version": SERVER_VERSION, "loaded_at": runtime.loaded_at, "uptime_s": round(time.time() - runtime.loaded_at, 1)}

    @app.post("/wake", dependencies=[Depends(require_token)])
    async def wake():
        return {"ok": True, "warm": True, "load_s": runtime.load_seconds}

    @app.get("/state", dependencies=[Depends(require_token)])
    async def state(speaker: str = Query(default="P1", pattern="^(S1|P1)$")):
        clips = [c for c in latest_by_id(speaker_dir(speaker) / "clips.jsonl").values() if not c.get("excluded")]
        return {
            "speaker": speaker,
            "model_version": runtime.model_version(speaker),
            "registry": read_json(runtime.registry_path(speaker), {}),
            "clips": {"total": len(clips), "train": sum(c.get("split") == "train" for c in clips), "test": sum(c.get("split") == "test" for c in clips)},
            "review_count": sum(c.get("trust") == "implicit" and not c.get("excluded") for c in clips),
            "settings": read_json(speaker_dir(speaker) / "settings.json", {}),
            "features": features().as_dict(),
            "speakers": list(SPEAKERS),
        }

    @app.get("/phrases", dependencies=[Depends(require_token)])
    async def phrases(speaker: str = Query(default="P1", pattern="^(S1|P1)$")):
        return {"phrases": [phrase.model_dump() for phrase in load_bank(speaker)]}

    @app.websocket("/ws")
    async def websocket(ws: WebSocket, token: str | None = Query(default=None)):
        if not token_matches(bearer(ws.headers.get("authorization")) or token):
            await ws.close(code=4401, reason="The app token is missing or wrong.")
            return
        await ws.accept()
        await run_session(ws, runtime)

    return app
