"""The pipeline settings the app may change, validated the same way from /settings and from hello."""

from pydantic import BaseModel, Field, ValidationError

from voice.tts.elevenlabs import voices


class SettingsIn(BaseModel):
    """Pipeline settings the app may change; omitted fields stay as they are."""

    voice_id: str | None = None
    before_speaking: str | None = Field(default=None, pattern="^(speak|check)$")
    speak_threshold: float | None = Field(default=None, ge=0.5, le=0.99)
    pick_threshold: float | None = Field(default=None, ge=0.1, le=0.99)
    endpoint_silence_ms: int | None = Field(default=None, ge=500, le=2000)
    learn_from_conversations: bool | None = None
    speech_rate: float | None = Field(default=None, ge=0.7, le=1.2)
    decide_provider: str | None = Field(default=None, pattern="^(jev|openai)$")


def valid_settings(raw: dict) -> dict:
    """The known, valid fields of `raw`; an unknown voice or an out-of-range value is dropped, not saved."""
    known = {key: value for key, value in raw.items() if key in SettingsIn.model_fields and value is not None}
    try:
        values = SettingsIn(**known).model_dump(exclude_none=True)
    except ValidationError as error:
        bad = {item["loc"][0] for item in error.errors()}
        values = SettingsIn(**{k: v for k, v in known.items() if k not in bad}).model_dump(exclude_none=True)
    if "voice_id" in values and values["voice_id"] not in {voice["id"] for voice in voices()["voices"]}:
        values.pop("voice_id")
    return values
