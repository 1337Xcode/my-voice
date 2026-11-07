"""Bearer-token checks for the app's routes and the trainer's internal route."""

import hmac

from fastapi import Header, HTTPException, Query

from voice.config import optional, require

# His access code for the demo, chosen by the team; ACCESS_CODE in .env overrides it.
DEFAULT_ACCESS_CODE = "heard"


def bearer(authorization: str | None) -> str | None:
    """The token from an 'Authorization: Bearer <token>' header, if present."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def same_secret(given: str | None, variable: str, purpose: str) -> bool:
    """True when `given` equals the secret in `variable`, compared in constant time."""
    expected = require(variable, purpose)
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def access_code() -> str:
    """The short code he types to unlock the web app; set ACCESS_CODE in .env to change it."""
    return optional("ACCESS_CODE", DEFAULT_ACCESS_CODE)


def token_matches(given: str | None) -> bool:
    """True when the given token is the app's APP_TOKEN or his access code."""
    if not given:
        return False
    if hmac.compare_digest(given.strip().lower().encode(), access_code().lower().encode()):
        return True
    return same_secret(given, "APP_TOKEN", "the app connection")


def require_token(authorization: str | None = Header(default=None), token: str | None = Query(default=None)) -> None:
    """Route dependency: rejects requests without the app's bearer token."""
    if not token_matches(bearer(authorization) or token):
        raise HTTPException(status_code=401, detail="The app token is missing or wrong.")


def require_internal_token(authorization: str | None = Header(default=None)) -> None:
    """Route dependency for trainer → server calls, which use INTERNAL_TOKEN."""
    if not same_secret(bearer(authorization), "INTERNAL_TOKEN", "the trainer's reload call"):
        raise HTTPException(status_code=401, detail="The internal token is missing or wrong.")


SPEAKER_PATTERN = "^(S1|P1)$"
