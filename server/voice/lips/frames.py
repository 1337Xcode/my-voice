"""One lip frame from `/ws/lips` (EXP-SPEC 9.2): the app's 104-byte header and its JPEG face crop.

Layout (little-endian), the same as `app/features/experiments/lips/frameCodec.ts`:
version u8, flags u8 (bit 0: face visible), 2 pad bytes, seq u32, device_ms f64, face box x y w h (0 to 1) 4×f32,
roll yaw pitch (degrees) 3×f32, mouth width, outer lip height, inner opening (crop px), mouth aspect, jaw open,
brightness 6×f32, keypoints right eye, left eye, nose tip, mouth centre (crop px) 8×f32, JPEG length u32.
"""

import struct
from dataclasses import dataclass

import numpy as np

HEADER = struct.Struct("<BB2xId4f3f6f8fI")
FORMAT_VERSION = 1
FACE_VISIBLE = 1


class BadFrame(ValueError):
    """A frame that doesn't follow the layout; it is dropped."""


@dataclass
class LipFrame:
    """A frame's geometry; `jpeg` is the face crop, kept only in memory and only until it is preprocessed."""

    seq: int
    device_ms: float
    face_visible: bool
    box: tuple[float, float, float, float]
    roll: float
    yaw: float
    pitch: float
    mouth_width: float
    outer_height: float
    inner_opening: float
    mouth_aspect: float
    jaw_open: float
    brightness: float
    keypoints: np.ndarray
    jpeg: bytes | None


def parse_frame(data: bytes) -> LipFrame:
    """Reads one binary frame; raises BadFrame when it is malformed."""
    if len(data) < HEADER.size:
        raise BadFrame(f"frame of {len(data)} bytes is shorter than the {HEADER.size}-byte header")
    values = HEADER.unpack_from(data)
    version, flags, seq, device_ms = values[:4]
    if version != FORMAT_VERSION:
        raise BadFrame(f"frame version {version}, expected {FORMAT_VERSION}")
    box, pose, shape, points, jpeg_length = values[4:8], values[8:11], values[11:17], values[17:25], values[25]
    if len(data) != HEADER.size + jpeg_length:
        raise BadFrame(f"frame says {jpeg_length} JPEG bytes but carries {len(data) - HEADER.size}")
    visible = bool(flags & FACE_VISIBLE)
    return LipFrame(
        seq=seq, device_ms=device_ms, face_visible=visible, box=tuple(box), roll=pose[0], yaw=pose[1], pitch=pose[2],
        mouth_width=shape[0], outer_height=shape[1], inner_opening=shape[2], mouth_aspect=shape[3], jaw_open=shape[4],
        brightness=shape[5], keypoints=np.asarray(points, dtype=np.float32).reshape(4, 2),
        jpeg=bytes(data[HEADER.size:]) if visible and jpeg_length else None,
    )
