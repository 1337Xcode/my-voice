"""The FastAPI app the speech server exposes: HTTP routes and the app's WebSocket."""

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from voice.config import SERVER_VERSION, MissingKey
from voice.calls import routes as calls
from voice.http import core, data, phrases, results, teach
from voice.http.auth import bearer, token_matches
from voice.runtime import Runtime
from voice.session import run_session


def create_app(runtime: Runtime) -> FastAPI:
    """Builds the web app around the container's loaded runtime."""
    app = FastAPI(title="My Voice speech server", version=SERVER_VERSION)
    app.state.runtime = runtime
    # Every route needs the bearer token, so any origin may call it (the web build uses this).
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(MissingKey)
    async def missing_key(_, error: MissingKey):
        return JSONResponse(status_code=503, content={"detail": str(error), "missing": error.variable})

    app.include_router(core.router)
    app.include_router(phrases.router)
    app.include_router(teach.router)
    app.include_router(results.router)
    app.include_router(data.router)
    app.include_router(calls.router)

    @app.websocket("/ws")
    async def websocket(ws: WebSocket, token: str | None = Query(default=None)):
        if not token_matches(bearer(ws.headers.get("authorization")) or token):
            await ws.close(code=4401, reason="The app token is missing or wrong.")
            return
        await ws.accept()
        await run_session(ws, runtime)

    return app
