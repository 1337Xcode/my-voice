"""The X0 coexistence test's verdict (EXP-SPEC 4.5 and 12): camera, microphone and voice together for 10 minutes."""

from pydantic import BaseModel, Field

X0_SECONDS = 600
X0_FPS = 24
# "24 fps for 10 minutes": at least this share of whole seconds at 24 or more (a single slow second is allowed).
X0_SECONDS_AT_FPS = 0.99
MIC_RATE_HZ = 16_000
MIC_RATE_TOLERANCE = 0.02


class CaptureReport(BaseModel):
    """What the phone measured during one capture test."""

    seconds: int = Field(ge=0)
    frames: int = Field(ge=0)
    face_frames: int = Field(ge=0)
    fps_per_second: list[int] = Field(max_length=7200)
    stalls: int = Field(ge=0)
    dropped: int = Field(ge=0)
    detect_ms_median: float | None = None
    jpeg_bytes_mean: float | None = None
    mic_frames: int = Field(ge=0)
    mic_gaps: int = Field(ge=0)
    mic_rate_hz: float | None = None
    voice_plays: int = Field(ge=0)


def capture_verdict(report: dict) -> dict:
    """The numbers the Experiments screen shows, and whether X0's acceptance rule is met."""
    per_second = report.get("fps_per_second") or []
    at_target = sum(1 for fps in per_second if fps >= X0_FPS)
    share = at_target / len(per_second) if per_second else 0.0
    rate = report.get("mic_rate_hz")
    rate_ok = rate is not None and abs(rate - MIC_RATE_HZ) <= MIC_RATE_HZ * MIC_RATE_TOLERANCE
    ordered = sorted(per_second)
    return {
        "seconds": report.get("seconds", 0),
        "fps_median": ordered[len(ordered) // 2] if ordered else None,
        "fps_lowest": ordered[0] if ordered else None,
        "seconds_at_24_pct": round(100 * share, 1),
        "face_visible_pct": round(100 * report["face_frames"] / report["frames"], 1) if report.get("frames") else None,
        "stalls": report.get("stalls", 0),
        "mic_gaps": report.get("mic_gaps", 0),
        "mic_rate_hz": rate,
        "detect_ms_median": report.get("detect_ms_median"),
        "met": (report.get("seconds", 0) >= X0_SECONDS and share >= X0_SECONDS_AT_FPS and report.get("stalls", 0) == 0
                and report.get("mic_gaps", 0) == 0 and rate_ok),
    }
