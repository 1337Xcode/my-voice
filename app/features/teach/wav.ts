/** Wraps captured 16 kHz mono 16-bit PCM as a WAV file in memory, and turns WAV bytes into something the player can open. */
import { File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';

import { SAMPLE_RATE_HZ } from '@/features/audio/pcm';

// A canonical PCM WAV header is 44 bytes.
const HEADER_BYTES = 44;

/** Joins the capture's PCM frames and prepends a WAV header (mono, 16-bit little-endian, 16 kHz). */
export function wavFromFrames(frames: ArrayBuffer[]): Uint8Array {
  const dataBytes = frames.reduce((sum, frame) => sum + frame.byteLength, 0);
  const out = new Uint8Array(HEADER_BYTES + dataBytes);
  const view = new DataView(out.buffer);
  const ascii = (offset: number, text: string) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  ascii(0, 'RIFF');
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, SAMPLE_RATE_HZ, true);
  view.setUint32(28, SAMPLE_RATE_HZ * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per sample frame
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, 'data');
  view.setUint32(40, dataBytes, true);
  let offset = HEADER_BYTES;
  for (const frame of frames) {
    out.set(new Uint8Array(frame), offset);
    offset += frame.byteLength;
  }
  return out;
}

/** Seconds of audio in a set of 16-bit mono frames. */
export function secondsOf(frames: ArrayBuffer[]): number {
  return frames.reduce((sum, frame) => sum + frame.byteLength, 0) / 2 / SAMPLE_RATE_HZ;
}

let webUrl: string | null = null;
let fileCounter = 0;

/** A playable URI for WAV bytes: a blob URL on web (the last one is released), a cache file on the phone. */
export async function wavUri(bytes: Uint8Array): Promise<string> {
  if (Platform.OS === 'web') {
    if (webUrl) URL.revokeObjectURL(webUrl);
    webUrl = URL.createObjectURL(new Blob([bytes.buffer as ArrayBuffer], { type: 'audio/wav' }));
    return webUrl;
  }
  // Alternate between two files so a new clip never overwrites the one playing.
  fileCounter = (fileCounter + 1) % 2;
  const file = new File(Paths.cache, `teach-play-${fileCounter}.wav`);
  file.create({ overwrite: true });
  await file.write(bytes);
  return file.uri;
}
