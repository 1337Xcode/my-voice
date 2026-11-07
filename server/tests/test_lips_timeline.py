"""Lips X0 on the server: the frame layout, the 60 s ring, the audio clock and the sync check's offset."""

import struct

import numpy as np
import pytest

from voice.audio.pcm import SAMPLE_RATE
from voice.lips.frames import HEADER, BadFrame, parse_frame
from voice.lips.sync import estimate_offset
from voice.lips.timeline import AudioClock, FrameRing


def frame_bytes(seq=7, device_ms=1_700_000_000_123.5, visible=True, jpeg=b"\xff\xd8jpeg\xff\xd9"):
    """A frame packed the way the app's frameCodec.ts packs it."""
    header = struct.pack("<BB2xId4f3f6f8fI", 1, 1 if visible else 0, seq, device_ms,
                         0.25, 0.2, 0.5, 0.6, 3.0, -12.5, 4.0, 40.0, 18.0, 6.0, 0.15, 0.3, 120.0,
                         55.0, 50.0, 105.0, 50.0, 80.0, 80.0, 80.0, 118.0, len(jpeg))
    return header + jpeg


def test_header_is_104_bytes_like_the_app():
    assert HEADER.size == 104


def test_parse_reads_every_field():
    frame = parse_frame(frame_bytes())
    assert frame.seq == 7 and frame.device_ms == 1_700_000_000_123.5 and frame.face_visible
    assert frame.box == pytest.approx((0.25, 0.2, 0.5, 0.6))
    assert (frame.roll, frame.yaw, frame.pitch) == pytest.approx((3.0, -12.5, 4.0))
    assert frame.mouth_width == pytest.approx(40.0) and frame.mouth_aspect == pytest.approx(0.15)
    assert frame.brightness == pytest.approx(120.0)
    assert frame.keypoints.tolist() == [[55.0, 50.0], [105.0, 50.0], [80.0, 80.0], [80.0, 118.0]]
    assert frame.jpeg == b"\xff\xd8jpeg\xff\xd9"


def test_no_face_frame_carries_no_jpeg():
    frame = parse_frame(frame_bytes(visible=False, jpeg=b""))
    assert not frame.face_visible and frame.jpeg is None


def test_bad_frames_are_refused():
    with pytest.raises(BadFrame):
        parse_frame(b"\x01" * 20)
    with pytest.raises(BadFrame):
        parse_frame(frame_bytes()[:-2])  # JPEG shorter than its length says


def test_ring_keeps_time_order_and_the_last_60_seconds():
    ring = FrameRing(size=3)
    for seq, ms in enumerate([100.0, 140.0, 120.0, 180.0]):
        ring.add(parse_frame(frame_bytes(seq=seq, device_ms=ms)))
    assert [f.device_ms for f in ring.frames] == [120.0, 140.0, 180.0]
    assert [f.device_ms for f in ring.between(130.0, 180.0)] == [140.0]


def test_audio_clock_uses_the_median_of_its_reports():
    clock = AudioClock()
    assert clock.device_ms(0) is None
    # 16000 samples a second; one report 30 ms late from network jitter.
    for n, t in [(16_000, 2_000.0), (32_000, 3_000.0), (48_000, 4_030.0)]:
        clock.report(n, t)
    assert clock.device_ms(0) == pytest.approx(1_000.0)
    assert clock.device_ms(8_000) == pytest.approx(1_500.0)


def pa_pa_pa(burst_ms, seconds=10):
    """Audio with a 150 ms burst at each time, plus a little room noise."""
    rng = np.random.default_rng(1)
    audio = rng.normal(0, 0.002, seconds * SAMPLE_RATE).astype(np.float32)
    for at in burst_ms:
        start = int(at * SAMPLE_RATE / 1000)
        audio[start : start + SAMPLE_RATE * 15 // 100] += rng.normal(0, 0.3, SAMPLE_RATE * 15 // 100).astype(np.float32)
    return audio


@pytest.mark.parametrize("video_early_ms", [80, -60, 0])
def test_sync_finds_the_offset_between_bursts_and_lip_openings(video_early_ms):
    bursts = [1000, 2600, 4200, 5800, 7400]
    audio_start = 50_000.0
    frame_ms = audio_start + np.arange(0, 10_000, 40, dtype=float)
    # The mouth opens with each burst; on the device clock the frames run `video_early_ms` early.
    opening = np.zeros(frame_ms.size)
    for at in bursts:
        seen = audio_start + at - video_early_ms
        opening += np.clip(1 - np.abs(frame_ms - (seen + 75)) / 110, 0, None)
    result = estimate_offset(pa_pa_pa(bursts), audio_start, frame_ms, opening)
    assert result.ok and result.bursts == 5
    assert result.offset_ms == pytest.approx(video_early_ms, abs=20)


def test_sync_refuses_silence():
    result = estimate_offset(np.zeros(10 * SAMPLE_RATE, dtype=np.float32), 0.0, np.arange(0, 10_000, 40.0), np.zeros(250))
    assert not result.ok and "pa" in result.reason
