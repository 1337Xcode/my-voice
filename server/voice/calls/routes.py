"""HTTP and WebSocket routes for calls: his call link, phone calls, the guest socket and Twilio's webhooks."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket
from pydantic import BaseModel, Field

from voice.calls.guest import run_guest
from voice.calls.twilio import PhoneError, check_number, credentials, public_host, run_media_stream, signature_matches, stream_twiml
from voice.http.auth import SPEAKER_PATTERN, require_token

router = APIRouter()


class CallIn(BaseModel):
    """A phone call he asked for. The opening line is his own text, spoken on answer and not kept."""

    number: str = Field(max_length=40)
    name: str = Field(default="", max_length=60)
    opening_line: str = Field(default="", max_length=300)


def _link(code: str) -> dict:
    return {"code": code, "url_path": f"/c/{code}"}


@router.post("/calls/link", dependencies=[Depends(require_token)])
async def call_link(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """His call code and the link a friend opens to call him (the code is created on first use)."""
    codes = request.app.state.runtime.calls.codes
    return _link(await asyncio.to_thread(codes.code_for, speaker))


@router.post("/calls/code/regenerate", dependencies=[Depends(require_token)])
async def regenerate_code(request: Request, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """A new call code; the old link stops working."""
    codes = request.app.state.runtime.calls.codes
    return _link(await asyncio.to_thread(codes.regenerate, speaker))


@router.post("/calls", dependencies=[Depends(require_token)])
async def start_phone_call(request: Request, body: CallIn, speaker: str = Query("P1", pattern=SPEAKER_PATTERN)):
    """Calls an ordinary phone number through Twilio; his open app session becomes his side of the call."""
    try:
        number = check_number(body.number)
    except PhoneError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    credentials()  # A missing Twilio variable answers 503 naming it (the app's MissingKey handler).
    calls = request.app.state.runtime.calls
    sessions = calls.sessions_for(speaker)
    if not sessions:
        raise HTTPException(status_code=409, detail="Open the app's Talk screen first, so the call can use your voice.")
    session = next((s for s in sessions if s.call is None), None)
    if session is None:
        raise HTTPException(status_code=409, detail="You're already on a call. Hang up first.")
    base_url = f"https://{public_host(request.headers)}"
    try:
        call = await calls.start_phone_call(session, number, body.name.strip(), body.opening_line.strip(), base_url)
    except PhoneError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"call_id": call.id, "state": call.state}


@router.post("/calls/{call_id}/hangup", dependencies=[Depends(require_token)])
async def hang_up(request: Request, call_id: str):
    """Ends a call from his side."""
    calls = request.app.state.runtime.calls
    call = calls.calls.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="That call has already ended.")
    await calls.hang_up(call)
    return {"call_id": call_id, "state": "ended"}


@router.websocket("/call/ws")
async def guest_socket(ws: WebSocket, code: str = Query(default="", max_length=12)):
    """A friend's browser calling him by his code; the code is the only authorisation."""
    await run_guest(ws, ws.app.state.runtime, code)


async def _signed_form(request: Request) -> dict[str, str]:
    """The webhook's form fields, after checking Twilio's signature over the exact URL it called."""
    form = {key: str(value) for key, value in (await request.form()).items()}
    url = f"https://{public_host(request.headers)}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"
    if not signature_matches([url], form, request.headers.get("x-twilio-signature")):
        raise HTTPException(status_code=403, detail="The Twilio signature is missing or wrong.")
    return form


@router.post("/twilio/voice")
async def twilio_voice(request: Request, call_id: str = Query(default="")):
    """Twilio's answer webhook: TwiML that streams the call's audio to /twilio/stream."""
    await _signed_form(request)
    call = request.app.state.runtime.calls.calls.get(call_id)
    if call is None or call.kind != "phone":
        return Response('<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>', media_type="text/xml")
    twiml = stream_twiml(f"wss://{public_host(request.headers)}/twilio/stream", call.id)
    return Response(twiml, media_type="text/xml")


@router.post("/twilio/status")
async def twilio_status(request: Request, call_id: str = Query(default="")):
    """Twilio's status callback: ringing, busy, no answer, completed."""
    form = await _signed_form(request)
    await request.app.state.runtime.calls.phone_status(call_id, form.get("CallStatus", ""))
    return Response(status_code=204)


@router.websocket("/twilio/stream")
async def twilio_stream(ws: WebSocket):
    """Twilio's bidirectional media stream for an answered phone call."""
    await run_media_stream(ws, ws.app.state.runtime.calls)
