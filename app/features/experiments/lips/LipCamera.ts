/**
 * Front-camera lip capture in the browser (EXP X0): the camera feeds a hidden video element (never shown), MediaPipe
 * finds the face at 25 frames a second, and each frame goes to the server's `/ws/lips` as a grey face crop plus its
 * geometry. The page only gets a light status about ten times a second.
 */
import { encodeFrame, type FrameRecord } from './frameCodec';
import { CROP_PX, faceCrop, headPose, MouthActivity, type Similarity } from './geometry';
import { loadLandmarker, type Landmarker, type LandmarkerResult } from './vision';

// Lip models are trained at 25 frames a second (EXP-SPEC 4.1).
const FRAME_INTERVAL_MS = 40;
const STATUS_EVERY_MS = 100;
const JPEG_QUALITY = 0.9;
// When the socket can't keep up, frames are dropped rather than queued without end.
const MAX_BUFFERED_BYTES = 256 * 1024;
// A gap this long between frames counts as a camera stall.
const STALL_MS = 200;
// Head turned further than this makes lip reading unreliable (EXP-SPEC 4.2).
const MAX_TURN_DEGREES = 25;
const DARK_BELOW = 55;
// Until his enrolment sets it, lips count as moving above this spread of the mouth opening.
const DEFAULT_MOVING_ABOVE = 0.02;

export type LipQuality = 'no_face' | 'turned' | 'dark' | 'far' | 'good';

export type LipStatus = {
  fps: number;
  faceVisible: boolean;
  quality: LipQuality;
  /** The spread of the mouth opening over 400 ms; above the threshold his lips are moving. */
  activity: number;
  moving: boolean;
  /** Where the face is in the camera's view (0 to 1) and how open the mouth is, for the positioning outline. */
  box: { x: number; y: number; w: number; h: number } | null;
  mouthAspect: number;
};

export type CaptureStats = {
  seconds: number;
  frames: number;
  faceFrames: number;
  /** Frames per second, per whole second of capture. */
  fpsPerSecond: number[];
  stalls: number;
  dropped: number;
  detectMsMedian: number | null;
  jpegBytesMean: number | null;
};

type Options = {
  serverUrl: string;
  token: string;
  sessionId: string;
  movingAbove?: number;
  onStatus: (status: LipStatus) => void;
  onError: (message: string) => void;
};

const deviceNow = () => performance.timeOrigin + performance.now();
const median = (values: number[]) => (values.length ? [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)] : null);

/** True when this browser can capture lips. */
export function canCaptureLips(): boolean {
  return typeof window !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia) && typeof WebSocket !== 'undefined';
}

export class LipCamera {
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private socket: WebSocket | null = null;
  private landmarker: Landmarker | null = null;
  private running = false;
  private seq = 0;
  private nextDueMs = 0;
  private lastFrameMs = 0;
  private lastStatusMs = 0;
  private activity = new MouthActivity();
  private latest: LipStatus = { fps: 0, faceVisible: false, quality: 'no_face', activity: 0, moving: false, box: null, mouthAspect: 0 };
  private frameTimes: number[] = [];
  private stats = { startedMs: 0, frames: 0, faceFrames: 0, stalls: 0, dropped: 0, detectMs: [] as number[], jpegBytes: [] as number[], perSecond: new Map<number, number>() };

  constructor(private options: Options) {}

  /** Opens the camera and the frame socket, then starts the frame loop. Rejects with a plain message. */
  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } }, audio: false })
      .catch((error: Error) => {
        throw new Error(error.name === 'NotAllowedError' ? 'Camera access is off. Allow the camera for this site in your browser settings, then try again.' : `The camera didn't start (${error.message}).`);
      });
    this.video = hiddenVideo(this.stream);
    await this.video.play();
    this.landmarker = await loadLandmarker();
    this.canvas = document.createElement('canvas');
    this.canvas.width = this.canvas.height = CROP_PX;
    await this.openSocket();
    this.running = true;
    this.stats.startedMs = deviceNow();
    this.schedule();
  }

  /** Stops the camera, the loop and the socket; safe to call more than once. */
  stop(): void {
    this.running = false;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.video?.remove();
    this.video = null;
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ type: 'lips_bye' }));
    this.socket?.close();
    this.socket = null;
  }

  /** Lets enrolment change when lips count as moving. */
  setMovingAbove(threshold: number): void {
    this.options.movingAbove = threshold;
  }

  /** What capture has measured since it started (for the capture test). */
  captureStats(): CaptureStats {
    const s = this.stats;
    const seconds = Math.floor((deviceNow() - s.startedMs) / 1000);
    // Whole seconds only: the current, unfinished second would read low.
    const fpsPerSecond = [...s.perSecond.entries()].filter(([second]) => second < seconds).map(([, count]) => count);
    return { seconds, frames: s.frames, faceFrames: s.faceFrames, fpsPerSecond, stalls: s.stalls, dropped: s.dropped, detectMsMedian: median(s.detectMs.slice(-500)), jpegBytesMean: s.jpegBytes.length ? Math.round(s.jpegBytes.reduce((a, b) => a + b, 0) / s.jpegBytes.length) : null };
  }

  private openSocket(): Promise<void> {
    const { serverUrl, token, sessionId } = this.options;
    const url = `${serverUrl.replace(/^http/, 'ws')}/ws/lips?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(sessionId)}`;
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(url);
      socket.binaryType = 'arraybuffer';
      socket.onopen = () => {
        socket.send(JSON.stringify({ type: 'lips_hello', session_id: sessionId, fps: 1000 / FRAME_INTERVAL_MS, crop_px: CROP_PX, device: navigator.userAgent.slice(0, 120) }));
        resolve();
      };
      socket.onerror = () => reject(new Error("The lip stream couldn't reach the speech server."));
      socket.onclose = (event) => {
        if (this.running) this.options.onError(event.reason || 'The lip stream closed. Turn the camera off and on to reconnect.');
      };
      this.socket = socket;
    });
  }

  private schedule(): void {
    const video = this.video;
    if (!this.running || !video) return;
    // requestVideoFrameCallback runs once per new camera frame and gives its capture time; rAF is the fallback.
    if ('requestVideoFrameCallback' in video) video.requestVideoFrameCallback((now, metadata) => this.onFrame(performance.timeOrigin + (metadata.captureTime ?? now)));
    else requestAnimationFrame(() => this.onFrame(deviceNow()));
  }

  private onFrame(deviceMs: number): void {
    if (!this.running) return;
    try {
      // Decimate to 25 a second by timestamp, keeping the phase so the rate stays even.
      if (deviceMs >= this.nextDueMs) {
        this.nextDueMs = deviceMs - this.nextDueMs > FRAME_INTERVAL_MS ? deviceMs + FRAME_INTERVAL_MS : this.nextDueMs + FRAME_INTERVAL_MS;
        this.capture(deviceMs);
      }
    } catch (error) {
      this.options.onError(`Lip tracking stopped (${(error as Error).message}).`);
      this.stop();
      return;
    }
    this.schedule();
  }

  private capture(deviceMs: number): void {
    const video = this.video!;
    const started = performance.now();
    const result = this.landmarker!.detectForVideo(video, started);
    this.stats.detectMs.push(performance.now() - started);
    this.count(deviceMs);
    const { record, transform } = this.record(result, deviceMs, video);
    if (!transform) {
      this.send(encodeFrame(record, null));
    } else {
      this.stats.faceFrames += 1;
      const pixels = this.drawCrop(video, transform);
      record.brightness = pixels.brightness;
      pixels.canvas.toBlob(
        (blob) => void blob?.arrayBuffer().then((bytes) => {
          this.stats.jpegBytes.push(bytes.byteLength);
          this.send(encodeFrame(record, new Uint8Array(bytes)));
        }),
        'image/jpeg',
        JPEG_QUALITY,
      );
    }
    this.report(record, deviceMs);
  }

  /** The frame's geometry record and its crop transform (none without a face); brightness is set once drawn. */
  private record(result: LandmarkerResult, deviceMs: number, video: HTMLVideoElement): { record: FrameRecord; transform: Similarity | null } {
    const landmarks = result.faceLandmarks[0];
    const base = { seq: this.seq++, deviceMs, jawOpen: 0, brightness: 0 };
    if (!landmarks) {
      const record = { ...base, faceVisible: false, box: { x: 0, y: 0, w: 0, h: 0 }, pose: { roll: 0, yaw: 0, pitch: 0 }, geometry: { mouthWidth: 0, outerHeight: 0, innerOpening: 0, mouthAspect: 0 }, keypoints: [] };
      return { record, transform: null };
    }
    const crop = faceCrop(landmarks, video.videoWidth, video.videoHeight);
    const matrix = result.facialTransformationMatrixes[0]?.data;
    const pose = matrix ? headPose(matrix) : { roll: 0, yaw: 0, pitch: 0 };
    const jawOpen = result.faceBlendshapes[0]?.categories.find((c) => c.categoryName === 'jawOpen')?.score ?? 0;
    return { record: { ...base, faceVisible: true, box: crop.box, pose, geometry: crop.geometry, jawOpen, keypoints: crop.keypoints }, transform: crop.transform };
  }

  /** Draws the face, roll removed, into the 160 px crop and turns it grey; returns the canvas and its mean level. */
  private drawCrop(video: HTMLVideoElement, transform: Similarity) {
    const canvas = this.canvas!;
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
    const cos = Math.cos(transform.angle) * transform.scale;
    const sin = Math.sin(transform.angle) * transform.scale;
    ctx.setTransform(cos, sin, -sin, cos, transform.tx, transform.ty);
    ctx.drawImage(video, 0, 0);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    const image = ctx.getImageData(0, 0, CROP_PX, CROP_PX);
    const data = image.data;
    let sum = 0;
    for (let i = 0; i < data.length; i += 4) {
      // ITU-R BT.601 luma, the same weights OpenCV's RGB→GRAY uses on the server.
      const grey = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      data[i] = data[i + 1] = data[i + 2] = grey;
      sum += grey;
    }
    ctx.putImageData(image, 0, 0);
    return { canvas, brightness: sum / (CROP_PX * CROP_PX) };
  }

  private send(frame: ArrayBuffer): void {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    if (socket.bufferedAmount > MAX_BUFFERED_BYTES) {
      this.stats.dropped += 1;
      return;
    }
    socket.send(frame);
  }

  private count(deviceMs: number): void {
    const s = this.stats;
    s.frames += 1;
    if (this.lastFrameMs && deviceMs - this.lastFrameMs > STALL_MS) s.stalls += 1;
    this.lastFrameMs = deviceMs;
    const second = Math.floor((deviceMs - s.startedMs) / 1000);
    s.perSecond.set(second, (s.perSecond.get(second) ?? 0) + 1);
    this.frameTimes.push(deviceMs);
    while (this.frameTimes.length && this.frameTimes[0] < deviceMs - 1000) this.frameTimes.shift();
  }

  private report(record: FrameRecord, deviceMs: number): void {
    const activity = record.faceVisible ? this.activity.add(deviceMs, record.geometry.mouthAspect) : (this.activity.reset(), 0);
    this.latest = {
      fps: this.frameTimes.length,
      faceVisible: record.faceVisible,
      quality: qualityOf(record),
      activity,
      moving: activity > (this.options.movingAbove ?? DEFAULT_MOVING_ABOVE),
      box: record.faceVisible ? record.box : null,
      mouthAspect: record.geometry.mouthAspect,
    };
    if (deviceMs - this.lastStatusMs >= STATUS_EVERY_MS) {
      this.lastStatusMs = deviceMs;
      this.options.onStatus(this.latest);
    }
  }
}

/** Grey, amber or green: is the mouth visible well enough to read (EXP-SPEC 4.2)? */
function qualityOf(record: FrameRecord): LipQuality {
  if (!record.faceVisible) return 'no_face';
  if (Math.abs(record.pose.yaw) > MAX_TURN_DEGREES || Math.abs(record.pose.pitch) > MAX_TURN_DEGREES) return 'turned';
  // A face under a fifth of the picture's width leaves too few pixels on the lips.
  if (record.box.w < 0.2) return 'far';
  if (record.brightness < DARK_BELOW) return 'dark';
  return 'good';
}

/** A video element the camera plays into: on the page (iOS only decodes frames for attached, playing videos) but invisible. */
function hiddenVideo(stream: MediaStream): HTMLVideoElement {
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.setAttribute('playsinline', '');
  video.setAttribute('aria-hidden', 'true');
  video.srcObject = stream;
  Object.assign(video.style, { position: 'fixed', left: '0', top: '0', width: '2px', height: '2px', opacity: '0.01', pointerEvents: 'none', zIndex: '-1' });
  document.body.appendChild(video);
  return video;
}
