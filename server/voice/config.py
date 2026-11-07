"""Server settings read from the environment, with errors that name the missing variable."""

import os
from dataclasses import dataclass
from pathlib import Path

# Where the two Modal volumes are mounted inside every container.
DATA_ROOT = Path(os.environ.get("SPEECH_DATA_ROOT", "/data"))
MODELS_ROOT = Path(os.environ.get("SPEECH_MODELS_ROOT", "/models"))
# Bundled read-only files: the default phrases and prompt lists.
ASSETS_ROOT = Path(os.environ.get("SPEECH_ASSETS_ROOT", Path(__file__).resolve().parent.parent / "assets"))

SERVER_VERSION = "0.1.0"
SPEAKERS = ("S1", "P1")


class MissingKey(RuntimeError):
    """Raised on first use of an integration whose environment variable is not set."""

    def __init__(self, variable: str, purpose: str):
        super().__init__(f"{variable} is not set, so {purpose} cannot run. Add it to .env and redeploy.")
        self.variable = variable


def require(variable: str, purpose: str) -> str:
    """Returns the variable's value, or raises MissingKey naming it."""
    value = os.environ.get(variable, "").strip()
    if not value:
        raise MissingKey(variable, purpose)
    return value


def optional(variable: str, default: str = "") -> str:
    """Returns the variable's value, or the default when unset or blank."""
    return os.environ.get(variable, "").strip() or default


@dataclass(frozen=True)
class Features:
    """Which optional parts of the product have their keys configured."""

    calls: bool
    toolkit: bool
    partials: bool
    # App-to-app calls by code need no keys, so they are always on.
    app_calls: bool = True
    # The experiments (EXP-SPEC): off unless REALTIME_VOICE=1 / LIPS=1, and even then only for apps that opt in.
    realtime_voice: bool = False
    lips: bool = False

    def as_dict(self) -> dict:
        return {"calls": self.calls, "toolkit": self.toolkit, "partials": self.partials, "app_calls": self.app_calls,
                "realtime_voice": self.realtime_voice, "lips": self.lips}


def features() -> Features:
    """Reads which optional integrations are configured right now."""
    calls = all(optional(v) for v in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"))
    return Features(calls=calls, toolkit=bool(optional("TOOLKIT_URL")), partials=False,
                    realtime_voice=optional("REALTIME_VOICE") == "1", lips=optional("LIPS") == "1")


def default_voice_id() -> str:
    """The ElevenLabs voice used until he picks one (the .env names it ELEVENLABS_VOICE_ID)."""
    return optional("ELEVENLABS_DEFAULT_VOICE_ID") or optional("ELEVENLABS_VOICE_ID")
