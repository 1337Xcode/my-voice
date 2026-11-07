/** PCM helpers for live capture: sample conversion, resampling, 100 ms framing and the input level. */

/** The server's audio format (spec 8.1): 16 kHz mono, 16-bit little-endian, 100 ms per WebSocket frame. */
export const SAMPLE_RATE_HZ = 16_000;
export const FRAME_SAMPLES = 1_600;
export const FRAME_BYTES = FRAME_SAMPLES * 2;

/** Decodes base64 into bytes without relying on Node's Buffer (absent in React Native). */
export function base64ToBytes(base64: string): Uint8Array {
  const binary = globalThis.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** Normalises whatever the recorder delivers into float samples in [-1, 1]. */
export function toFloat32(data: string | Float32Array | Int16Array | number[]): Float32Array {
  if (data instanceof Float32Array) return data;
  if (Array.isArray(data)) return Float32Array.from(data);
  if (data instanceof Int16Array) return Float32Array.from(data, (s) => s / 32768);
  // A base64 string carries raw 16-bit little-endian PCM.
  const bytes = base64ToBytes(data);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const out = new Float32Array(Math.floor(bytes.byteLength / 2));
  for (let i = 0; i < out.length; i += 1) out[i] = view.getInt16(i * 2, true) / 32768;
  return out;
}

/** Linear-interpolation resampler, used only when the platform delivers a rate other than 16 kHz. */
export function resample(input: Float32Array, fromHz: number, toHz: number): Float32Array {
  if (fromHz === toHz) return input;
  const ratio = fromHz / toHz;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i += 1) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    out[i] = input[left] + (input[right] - input[left]) * (position - left);
  }
  return out;
}

/** Collects samples and hands back complete 100 ms frames of 16-bit little-endian PCM (3,200 bytes each). */
export class FrameAssembler {
  private pending = new Float32Array(FRAME_SAMPLES);
  private filled = 0;

  /** Adds samples; returns every frame they completed. */
  push(samples: Float32Array): ArrayBuffer[] {
    const frames: ArrayBuffer[] = [];
    let offset = 0;
    while (offset < samples.length) {
      const take = Math.min(FRAME_SAMPLES - this.filled, samples.length - offset);
      this.pending.set(samples.subarray(offset, offset + take), this.filled);
      this.filled += take;
      offset += take;
      if (this.filled === FRAME_SAMPLES) {
        frames.push(encodeInt16LE(this.pending));
        this.filled = 0;
      }
    }
    return frames;
  }

  /** The partly filled last frame, zero-padded, or null when empty; used when the turn ends. */
  flush(): ArrayBuffer | null {
    if (this.filled === 0) return null;
    this.pending.fill(0, this.filled);
    this.filled = 0;
    return encodeInt16LE(this.pending);
  }
}

/** Float samples to 16-bit little-endian bytes, clipping at full scale. */
export function encodeInt16LE(samples: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < samples.length; i += 1) {
    const clipped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(i * 2, clipped < 0 ? clipped * 32768 : clipped * 32767, true);
  }
  return buffer;
}

// The meter maps -60 dBFS (a quiet room) to 0 and -10 dBFS (loud speech close to the mic) to 1.
const FLOOR_DB = -60;
const CEILING_DB = -10;

/** The loudness of a block of samples as a 0 to 1 meter value. */
export function levelOf(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) sum += samples[i] * samples[i];
  const db = 10 * Math.log10(sum / samples.length + 1e-12);
  return Math.max(0, Math.min(1, (db - FLOOR_DB) / (CEILING_DB - FLOOR_DB)));
}

// Background above about -35 dBFS between his words makes recognition harder; say so.
const NOISY_FLOOR_LEVEL = (-35 - FLOOR_DB) / (CEILING_DB - FLOOR_DB);

/** True when the quietest fifth of recent levels (the room between words) is loud. */
export function isNoisy(recentLevels: number[]): boolean {
  if (recentLevels.length < 15) return false;
  const sorted = [...recentLevels].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length * 0.2)] > NOISY_FLOOR_LEVEL;
}
