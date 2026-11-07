/**
 * Loads MediaPipe's Face Landmarker (EXP X0) from its pinned CDN build, only when the lips screen opens, so the
 * core app's bundle never carries it. GPU first; CPU when the browser can't give it a WebGL context.
 */
const VERSION = '1.2.2';
const BUNDLE_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}/vision_bundle.mjs`;
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}/wasm`;
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

/** The parts of the FaceLandmarker result this app reads (types from the package's vision.d.ts at 1.2.2). */
export type LandmarkerResult = {
  faceLandmarks: { x: number; y: number; z: number }[][];
  faceBlendshapes: { categories: { categoryName: string; score: number }[] }[];
  facialTransformationMatrixes: { rows: number; columns: number; data: number[] }[];
};

export type Landmarker = {
  detectForVideo: (video: HTMLVideoElement, timestampMs: number) => LandmarkerResult;
  close: () => void;
};

type VisionModule = {
  FilesetResolver: { forVisionTasks: (wasmUrl: string) => Promise<unknown> };
  FaceLandmarker: { createFromOptions: (fileset: unknown, options: object) => Promise<Landmarker> };
};

// A real dynamic import of a URL, written so the bundler leaves it alone instead of trying to bundle it.
const importUrl = new Function('url', 'return import(url)') as (url: string) => Promise<VisionModule>;

let loading: Promise<Landmarker> | null = null;

/** The one Face Landmarker, created on first use; a failed load can be retried. */
export function loadLandmarker(): Promise<Landmarker> {
  loading ??= create().catch((error: Error) => {
    loading = null;
    throw new Error(`The lip tracker didn't load. Check the connection and try again. (${error.message})`);
  });
  return loading;
}

async function create(): Promise<Landmarker> {
  const vision = await importUrl(BUNDLE_URL);
  const fileset = await vision.FilesetResolver.forVisionTasks(WASM_URL);
  const options = (delegate: 'GPU' | 'CPU') => ({
    baseOptions: { modelAssetPath: MODEL_URL, delegate },
    runningMode: 'VIDEO',
    // One face: MediaPipe smooths landmarks over time only with numFaces 1, and the front camera sees him.
    numFaces: 1,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: true,
  });
  try {
    return await vision.FaceLandmarker.createFromOptions(fileset, options('GPU'));
  } catch {
    return vision.FaceLandmarker.createFromOptions(fileset, options('CPU'));
  }
}
