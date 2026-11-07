/**
 * One lip frame on `/ws/lips` (EXP-SPEC 9.2): a 104-byte little-endian header, then the JPEG face crop.
 * The server reads the same layout (`server/voice/lips/frames.py`); docs/RUNBOOK.md lists it byte by byte.
 */
import type { MouthGeometry, Point } from './geometry';

export const HEADER_BYTES = 104;
export const FORMAT_VERSION = 1;
// Flag bit 0: a face was found in this frame (otherwise the geometry is zeros and no JPEG follows).
export const FACE_VISIBLE = 1;

export type FrameRecord = {
  seq: number;
  /** Device clock (performance.timeOrigin + performance.now()), ms. */
  deviceMs: number;
  faceVisible: boolean;
  /** Face box in the video, 0 to 1. */
  box: { x: number; y: number; w: number; h: number };
  pose: { roll: number; yaw: number; pitch: number };
  geometry: MouthGeometry;
  /** MediaPipe's jawOpen blendshape, 0 to 1. */
  jawOpen: number;
  /** Mean grey level of the crop, 0 to 255. */
  brightness: number;
  /** Right eye, left eye, nose tip, mouth centre, in crop pixels. */
  keypoints: Point[];
};

/** Packs one frame: header then JPEG bytes (none when no face is visible). */
export function encodeFrame(record: FrameRecord, jpeg: Uint8Array | null): ArrayBuffer {
  const length = jpeg?.byteLength ?? 0;
  const buffer = new ArrayBuffer(HEADER_BYTES + length);
  const view = new DataView(buffer);
  let at = 0;
  const u8 = (v: number) => view.setUint8(at++, v);
  const u32 = (v: number) => {
    view.setUint32(at, v, true);
    at += 4;
  };
  const f32 = (v: number) => {
    view.setFloat32(at, Number.isFinite(v) ? v : 0, true);
    at += 4;
  };
  u8(FORMAT_VERSION);
  u8(record.faceVisible ? FACE_VISIBLE : 0);
  at += 2; // padding, keeps the float fields aligned
  u32(record.seq);
  view.setFloat64(at, record.deviceMs, true);
  at += 8;
  [record.box.x, record.box.y, record.box.w, record.box.h].forEach(f32);
  [record.pose.roll, record.pose.yaw, record.pose.pitch].forEach(f32);
  const g = record.geometry;
  [g.mouthWidth, g.outerHeight, g.innerOpening, g.mouthAspect, record.jawOpen, record.brightness].forEach(f32);
  for (let i = 0; i < 4; i += 1) {
    f32(record.keypoints[i]?.x ?? 0);
    f32(record.keypoints[i]?.y ?? 0);
  }
  u32(length); // at = 100 here; the JPEG starts at 104
  if (jpeg) new Uint8Array(buffer, HEADER_BYTES).set(jpeg);
  return buffer;
}
