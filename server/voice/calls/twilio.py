"""Phone calls through Twilio (spec 13): number checks, the REST calls, TwiML, webhook signatures and the media stream.

Sources: Twilio's Call resource, TwiML <Stream>, Media Streams WebSocket messages and webhook security pages
(docs/API-NOTES.md section 4). The callee's audio is decoded in memory for captions and never stored.
"""

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
from xml.sax.saxutils import quoteattr

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from voice.calls.mulaw import PhoneAudioDecoder, pulse_tone
from voice.config import optional, require
from voice.tts.elevenlabs import CALL_FORMAT

log = logging.getLogger("voice.calls.twilio")

API_ROOT = "https://api.twilio.com/2010-04-01"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
RETRY_DELAYS_S = (0.5, 1.5)
RING_TIMEOUT_S = 45
# E.164: a plus, a country code that does not start with 0, then the rest; 8 to 15 digits in all.
E164 = re.compile(r"\+[1-9]\d{7,14}")
EMERGENCY_NUMBERS = ("999", "112", "911", "000", "119", "110")
EMERGENCY_NOTE = ("Emergency numbers can't be called through the app. Call them directly from your phone, "
                  "or use emergencySMS.")
# 20 ms of 8 kHz μ-law per media message, and a pulse every 1.5 s while he is working out a sentence.
CHUNK_BYTES = 160
PULSE_INTERVAL_S = 1.5
PULSE_STATES = ("thinking", "choosing")
PULSE = pulse_tone()
# Twilio's call statuses (StatusCallback) and what each means for the call.
TWILIO_STATUSES = {
    "queued": ("dialling", ""),
    "initiated": ("dialling", ""),
    "ringing": ("ringing", ""),
    "completed": ("ended", "The call ended."),
    "busy": ("failed", "The line was busy."),
    "no-answer": ("failed", "No answer."),
    "failed": ("failed", "The call could not be connected."),
    "canceled": ("ended", "The call was cancelled."),
}


class PhoneError(RuntimeError):
    """A plain-language failure placing or ending a phone call."""


class TwilioCall(BaseModel):
    """The fields we use from Twilio's Call resource."""

    sid: str
    status: str


class StreamStart(BaseModel):
    """The `start` message that opens a media stream."""

    class Start(BaseModel):
        callSid: str
        customParameters: dict[str, str] = {}

    streamSid: str
    start: Start


def check_number(raw: str) -> str:
    """The number in E.164 form; raises PhoneError for emergency numbers or anything that isn't E.164."""
    number = re.sub(r"[\s\-().]", "", raw or "")
    digits = number.lstrip("+")
    # Also catches a country code or trunk prefix in front of a short emergency number, like +44 999 or 00112.
    if any(digits == short or (len(digits) <= 6 and digits.endswith(short)) for short in EMERGENCY_NUMBERS):
        raise PhoneError(EMERGENCY_NOTE)
    if not E164.fullmatch(number):
        raise PhoneError("Enter the number in international form, starting with + and the country code, like +44 7700 900123.")
    return number


def credentials() -> tuple[str, str, str]:
    """Account SID, auth token and our number; raises MissingKey naming the first one not set."""
    purpose = "phone calls"
    return require("TWILIO_ACCOUNT_SID", purpose), require("TWILIO_AUTH_TOKEN", purpose), require("TWILIO_FROM_NUMBER", purpose)


def signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Twilio's X-Twilio-Signature: HMAC-SHA1 over the URL plus each sorted parameter's name and value, base64."""
    payload = url + "".join(f"{name}{params[name]}" for name in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def signature_matches(urls: list[str], params: dict[str, str], given: str | None) -> bool:
    """True when `given` is Twilio's signature for any of the URLs (needs TWILIO_AUTH_TOKEN)."""
    token = optional("TWILIO_AUTH_TOKEN")
    if not token or not given:
        return False
    return any(hmac.compare_digest(signature(url, params, token), given) for url in urls)


def stream_twiml(stream_url: str, call_id: str) -> str:
    """TwiML that connects the answered call to our bidirectional media stream, tagged with the call id."""
    return (f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Connect><Stream url={quoteattr(stream_url)}>"
            f"<Parameter name=\"call_id\" value={quoteattr(call_id)}/></Stream></Connect></Response>")


async def _twilio_post(http: httpx.AsyncClient, path: str, data: dict) -> dict:
    """One form POST to the account's REST API: retried twice on 429, 5xx and network errors."""
    account, token, _ = credentials()
    url = f"{API_ROOT}/Accounts/{account}/{path}"
    for attempt in range(len(RETRY_DELAYS_S) + 1):
        retry = attempt < len(RETRY_DELAYS_S)
        try:
            response = await http.post(url, data=data, auth=(account, token), timeout=TIMEOUT)
        except httpx.HTTPError as error:
            if retry:
                await asyncio.sleep(RETRY_DELAYS_S[attempt])
                continue
            raise PhoneError(f"Could not reach Twilio ({type(error).__name__}). Check the connection and try again.") from error
        if response.status_code in (200, 201):
            return response.json()
        if response.status_code in (401, 403):
            raise PhoneError("Twilio refused the account details. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")
        if retry and (response.status_code == 429 or response.status_code >= 500):
            await asyncio.sleep(RETRY_DELAYS_S[attempt])
            continue
        raise PhoneError(f"Twilio could not do that ({response.status_code}): {_twilio_message(response)}")
    raise PhoneError("Twilio is busy. Try again in a moment.")


def _twilio_message(response: httpx.Response) -> str:
    """Twilio's own error message from an error body, or the start of the body."""
    try:
        return str(response.json().get("message") or response.text[:200])
    except ValueError:
        return response.text[:200]


async def create_call(http: httpx.AsyncClient, number: str, voice_url: str, status_url: str) -> str:
    """Places the call; Twilio fetches `voice_url` on answer and reports progress to `status_url`. Returns its SID."""
    _, _, our_number = credentials()
    data = {"To": number, "From": our_number, "Url": voice_url, "Method": "POST", "StatusCallback": status_url,
            "StatusCallbackMethod": "POST", "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
            "Timeout": str(RING_TIMEOUT_S)}
    body = await _twilio_post(http, "Calls.json", data)
    try:
        return TwilioCall.model_validate(body).sid
    except ValidationError as error:
        raise PhoneError("Twilio answered without a call id. Try again.") from error


async def end_call(http: httpx.AsyncClient, call_sid: str) -> None:
    """Hangs up a call that is ringing or in progress."""
    await _twilio_post(http, f"Calls/{call_sid}.json", {"Status": "completed"})


class PhoneLine:
    """The callee's side of a phone call: the Twilio call and, once answered, its media stream."""

    audio_format = CALL_FORMAT

    def __init__(self, http: httpx.AsyncClient, opening_line: str):
        self.http = http
        self.opening_line = opening_line
        self.call_sid: str | None = None
        self.ws: WebSocket | None = None
        self.stream_sid: str | None = None
        self.send_lock = asyncio.Lock()
        self.pulse_task: asyncio.Task | None = None
        self.clips_sent = 0

    def attach(self, ws: WebSocket, stream_sid: str) -> None:
        """The callee answered and Twilio opened the media stream."""
        self.ws, self.stream_sid = ws, stream_sid

    async def status(self, message: dict) -> None:
        """The callee has no screen; call status is shown only in his app."""

    async def before_speaking(self, text: str) -> None:
        """His sentence is coming: stop the waiting pulse."""
        self._stop_pulse()

    async def play(self, audio: bytes) -> None:
        """Clears anything still queued, then sends the clip as 20 ms media messages and a mark."""
        self._stop_pulse()
        await self._send({"event": "clear"})
        await self._send_audio(audio)
        self.clips_sent += 1
        await self._send({"event": "mark", "mark": {"name": f"sentence-{self.clips_sent}"}})

    async def show_state(self, state: str) -> None:
        """Pulses while he is working out a sentence; silence otherwise."""
        if state in PULSE_STATES:
            if self.pulse_task is None or self.pulse_task.done():
                self.pulse_task = asyncio.create_task(self._pulse())
        else:
            self._stop_pulse()

    async def close(self, hang_up: bool) -> None:
        """Ends the stream, and the call itself when `hang_up` (Twilio has not already ended it)."""
        self._stop_pulse()
        if hang_up and self.call_sid:
            try:
                await end_call(self.http, self.call_sid)
            except PhoneError as error:
                log.warning("hang up failed: %s", error)
        if self.ws is not None:
            try:
                await self.ws.close()
            except RuntimeError:
                pass

    async def _pulse(self) -> None:
        while True:
            await self._send_audio(PULSE)
            await asyncio.sleep(PULSE_INTERVAL_S)

    def _stop_pulse(self) -> None:
        if self.pulse_task is not None:
            self.pulse_task.cancel()
            self.pulse_task = None

    async def _send_audio(self, audio: bytes) -> None:
        for start in range(0, len(audio), CHUNK_BYTES):
            payload = base64.b64encode(audio[start : start + CHUNK_BYTES]).decode("ascii")
            await self._send({"event": "media", "media": {"payload": payload}})

    async def _send(self, message: dict) -> None:
        """Sends one message on the media stream; a closed or not-yet-open stream drops it."""
        if self.ws is None:
            return
        try:
            async with self.send_lock:
                await self.ws.send_text(json.dumps({**message, "streamSid": self.stream_sid}))
        except (RuntimeError, WebSocketDisconnect):
            log.info("media stream closed; dropped %s", message.get("event"))



def public_host(headers) -> str:
    """The host name Twilio used to reach us (the proxy's forwarded host when there is one)."""
    return (headers.get("x-forwarded-host") or headers.get("host") or "").split(",")[0].strip()


async def run_media_stream(ws: WebSocket, calls) -> None:
    """Serves one Twilio media stream: links it to its call on `start`, captions the callee, ends the call on `stop`."""
    url = f"wss://{public_host(ws.headers)}{ws.url.path}"
    # Twilio's security page: for a WebSocket handshake, also try the URL with a trailing slash.
    if not signature_matches([url, url + "/"], {}, ws.headers.get("x-twilio-signature")):
        log.warning("media stream refused: signature does not match %s", url)
        await ws.close(code=4403, reason="The Twilio signature is missing or wrong.")
        return
    await ws.accept()
    call, decoder = None, PhoneAudioDecoder()
    try:
        while True:
            event = _read_event(await ws.receive_text())
            kind = event.get("event")
            if kind == "start":
                call = await calls.phone_answered(ws, event)
                if call is None:
                    return
            elif kind == "media" and call is not None:
                _hear_media(call, decoder, event)
            elif kind == "stop":
                return
    except WebSocketDisconnect:
        return
    finally:
        if call is not None:
            await calls.finish(call, "ended", "The call ended.", "", hang_up=False)


def _read_event(raw: str) -> dict:
    """One media-stream message as a dict; anything unreadable becomes an empty event that is ignored."""
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("unreadable media stream message dropped")
        return {}
    return event if isinstance(event, dict) else {}


def _hear_media(call, decoder: PhoneAudioDecoder, event: dict) -> None:
    """Feeds one inbound μ-law chunk to the call's captions."""
    media = event.get("media") or {}
    if media.get("track", "inbound") != "inbound" or call.captions is None:
        return
    try:
        payload = base64.b64decode(media.get("payload", ""), validate=True)
    except (binascii.Error, ValueError):
        log.warning("media chunk with bad base64 dropped")
        return
    call.captions.add(decoder.decode(payload))
