/** Lip geometry from MediaPipe's 478-point face mesh (EXP X0): mouth opening, head pose and the face-crop transform. */

export type Point = { x: number; y: number };

/** Mesh indices: mouth corners, outer lip top and bottom, inner lip top and bottom, nose tip, eye contours. */
export const MESH = {
  mouthLeft: 61,
  mouthRight: 291,
  outerTop: 0,
  outerBottom: 17,
  innerTop: 13,
  innerBottom: 14,
  noseTip: 1,
  // The subject's right eye (on the viewer's left) and left eye, as rings of contour points.
  rightEye: [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
  leftEye: [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466],
} as const;

/** The face crop sent to the server: 160 px square, eyes 50 px apart with their midpoint 50 px from the top. */
export const CROP_PX = 160;
const CROP_EYE_DISTANCE_PX = 50;
const CROP_EYE_MID: Point = { x: 80, y: 50 };

const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
const mean = (points: Point[]): Point => ({ x: points.reduce((s, p) => s + p.x, 0) / points.length, y: points.reduce((s, p) => s + p.y, 0) / points.length });

/** A similarity transform: rotate by `angle`, scale by `scale`, then translate. */
export type Similarity = { scale: number; angle: number; tx: number; ty: number };

export function applySimilarity(t: Similarity, p: Point): Point {
  const cos = Math.cos(t.angle) * t.scale;
  const sin = Math.sin(t.angle) * t.scale;
  return { x: cos * p.x - sin * p.y + t.tx, y: sin * p.x + cos * p.y + t.ty };
}

/** Head yaw, pitch and roll in degrees from MediaPipe's 4x4 column-major facial transformation matrix. */
export function headPose(matrix: ArrayLike<number>): { yaw: number; pitch: number; roll: number } {
  // r(i, j) is row i, column j of the rotation, with each column's scale removed.
  const scale = (j: number) => Math.hypot(matrix[j * 4], matrix[j * 4 + 1], matrix[j * 4 + 2]) || 1;
  const r = (i: number, j: number) => matrix[j * 4 + i] / scale(j);
  const degrees = (radians: number) => (radians * 180) / Math.PI;
  return {
    yaw: degrees(Math.atan2(r(0, 2), r(2, 2))),
    pitch: degrees(Math.asin(Math.max(-1, Math.min(1, -r(1, 2))))),
    roll: degrees(Math.atan2(r(1, 0), r(1, 1))),
  };
}

export type MouthGeometry = {
  /** Corner to corner, in crop pixels. */
  mouthWidth: number;
  /** Outer lip top to bottom, in crop pixels. */
  outerHeight: number;
  /** Inner lip gap, in crop pixels. */
  innerOpening: number;
  /** Inner opening over mouth width: 0 closed, about 0.5 wide open. */
  mouthAspect: number;
};

/**
 * The transform from video pixels to the face crop (roll removed, eyes level and a fixed distance apart), the
 * mouth geometry in crop pixels, and the four alignment points the lip models use (right eye, left eye, nose tip,
 * mouth centre), also in crop pixels.
 */
export function faceCrop(landmarks: Point[], videoWidth: number, videoHeight: number) {
  const px = (i: number): Point => ({ x: landmarks[i].x * videoWidth, y: landmarks[i].y * videoHeight });
  const rightEye = mean(MESH.rightEye.map(px));
  const leftEye = mean(MESH.leftEye.map(px));
  const eyeMid = mean([rightEye, leftEye]);
  const angle = -Math.atan2(leftEye.y - rightEye.y, leftEye.x - rightEye.x);
  const scale = CROP_EYE_DISTANCE_PX / Math.max(1, distance(rightEye, leftEye));
  const rotated = applySimilarity({ scale, angle, tx: 0, ty: 0 }, eyeMid);
  const transform: Similarity = { scale, angle, tx: CROP_EYE_MID.x - rotated.x, ty: CROP_EYE_MID.y - rotated.y };
  const crop = (i: number) => applySimilarity(transform, px(i));
  const mouthWidth = distance(crop(MESH.mouthLeft), crop(MESH.mouthRight));
  const innerOpening = distance(crop(MESH.innerTop), crop(MESH.innerBottom));
  const geometry: MouthGeometry = {
    mouthWidth,
    outerHeight: distance(crop(MESH.outerTop), crop(MESH.outerBottom)),
    innerOpening,
    mouthAspect: mouthWidth > 0 ? innerOpening / mouthWidth : 0,
  };
  const mouthCentre = mean([crop(MESH.innerTop), crop(MESH.innerBottom), crop(MESH.mouthLeft), crop(MESH.mouthRight)]);
  const keypoints = [applySimilarity(transform, rightEye), applySimilarity(transform, leftEye), crop(MESH.noseTip), mouthCentre];
  const xs = landmarks.map((l) => l.x);
  const ys = landmarks.map((l) => l.y);
  const box = { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
  return { transform, geometry, keypoints, box };
}

/** The moving spread of the mouth opening: the standard deviation over the last `windowMs` (lips moving vs still). */
export class MouthActivity {
  private samples: { at: number; value: number }[] = [];

  constructor(private windowMs = 400) {}

  add(at: number, mouthAspect: number): number {
    this.samples.push({ at, value: mouthAspect });
    while (this.samples.length && this.samples[0].at < at - this.windowMs) this.samples.shift();
    const values = this.samples.map((s) => s.value);
    const average = values.reduce((s, v) => s + v, 0) / values.length;
    return Math.sqrt(values.reduce((s, v) => s + (v - average) ** 2, 0) / values.length);
  }

  reset(): void {
    this.samples = [];
  }
}
