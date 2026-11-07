/** Streamed voice (EXP R1): plays PCM chunks as they arrive, gaplessly, with the browser's Web Audio API. */
import { markVoicePlaying, onVoicePlaying } from '@/features/audio/playback';
import { base64ToBytes } from '@/features/audio/pcm';

// A little lead so a chunk that arrives a few ms late still joins the previous one without a click.
const SCHEDULE_LEAD_S = 0.03;

type Stream = {
  key: string;
  sampleRateHz: number;
  // Every chunk's samples, kept so Replay can play the whole sentence again as one clip.
  chunks: Float32Array[];
  sources: Set<AudioBufferSourceNode>;
  nextStartAt: number;
  finalSeen: boolean;
  startedAt: number | null;
  onStarted: (() => void) | null;
};

let context: AudioContext | null = null;
let current: Stream | null = null;
// The last sentence that played to the end, kept for Replay.
let lastFinished: Stream | null = null;
// True while this module itself is changing the shared playing flag, so its own change is not taken as a stop.
let selfChanging = false;

/** True when this browser can play streamed voice. */
export function canStreamVoice(): boolean {
  return typeof window !== 'undefined' && typeof (window.AudioContext ?? (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext) === 'function';
}

function audioContext(): AudioContext {
  if (!context) {
    const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    context = new Context();
  }
  return context;
}

/** Starts the audio context now; call inside a tap. */
export function resumeStreamAudio(): void {
  if (canStreamVoice()) void audioContext().resume().catch(() => undefined);
}

/**
 * Browsers only start sound a tap started (iOS Safari above all): resumes the audio context on the first tap after
 * this is called, then stays unlocked for the page's life. Returns the function that removes the listener.
 */
export function unlockOnNextTap(): () => void {
  if (!canStreamVoice()) return () => undefined;
  const resume = () => void audioContext().resume().catch(() => undefined);
  document.addEventListener('pointerdown', resume, { capture: true });
  document.addEventListener('touchend', resume, { capture: true });
  return () => {
    document.removeEventListener('pointerdown', resume, { capture: true });
    document.removeEventListener('touchend', resume, { capture: true });
  };
}

function setPlaying(next: boolean): void {
  selfChanging = true;
  markVoicePlaying(next);
  selfChanging = false;
}

// Anything else stopping the voice (a new turn, Replay of an MP3, Dismiss) stops the stream too.
onVoicePlaying((isPlaying) => {
  if (!isPlaying && !selfChanging) stopStream();
});

/** 16-bit little-endian PCM in base64 → float samples. */
function pcm16ToFloat(base64: string): Float32Array {
  const bytes = base64ToBytes(base64);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const out = new Float32Array(bytes.byteLength >> 1);
  for (let i = 0; i < out.length; i += 1) out[i] = view.getInt16(i * 2, true) / 32768;
  return out;
}

/** Stops the stream that is playing, if any. */
export function stopStream(): void {
  const stream = current;
  if (!stream) return;
  current = null;
  stream.sources.forEach((source) => {
    source.onended = null;
    try {
      source.stop();
    } catch {
      // A source that never started throws on stop; nothing to undo.
    }
  });
  setPlaying(false);
}

/**
 * Adds one chunk of the sentence `key` (a turn id). The first chunk of a new key replaces whatever was playing.
 * `onStarted` runs once, when the first sound is scheduled.
 */
export function playChunk(key: string, base64Pcm: string, sampleRateHz: number, final: boolean, onStarted?: () => void): void {
  const ctx = audioContext();
  if (!current || current.key !== key) {
    stopStream();
    current = { key, sampleRateHz, chunks: [], sources: new Set(), nextStartAt: 0, finalSeen: false, startedAt: null, onStarted: onStarted ?? null };
  }
  const stream = current;
  stream.finalSeen ||= final;
  const samples = base64Pcm ? pcm16ToFloat(base64Pcm) : new Float32Array(0);
  if (samples.length) {
    stream.chunks.push(samples);
    const buffer = ctx.createBuffer(1, samples.length, sampleRateHz);
    buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime + SCHEDULE_LEAD_S, stream.nextStartAt);
    source.start(startAt);
    stream.nextStartAt = startAt + buffer.duration;
    stream.sources.add(source);
    source.onended = () => {
      stream.sources.delete(source);
      finishIfDone(stream);
    };
    if (stream.startedAt === null) {
      stream.startedAt = Date.now();
      setPlaying(true);
      stream.onStarted?.();
    }
  }
  finishIfDone(stream);
}

/** The sentence is over once its final chunk has arrived and every scheduled buffer has played. */
function finishIfDone(stream: Stream): void {
  if (stream !== current || !stream.finalSeen || stream.sources.size > 0) return;
  current = null;
  setPlaying(false);
  lastFinished = stream;
}

/** The sentence `key` as one WAV blob URL for Replay, once its stream has finished; null otherwise. */
export function streamedClipUrl(key: string): string | null {
  const stream = lastFinished?.key === key ? lastFinished : current?.key === key && current.finalSeen ? current : null;
  if (!stream || !stream.chunks.length) return null;
  const total = stream.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const view = new DataView(new ArrayBuffer(44 + total * 2));
  const ascii = (offset: number, text: string) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  ascii(0, 'RIFF');
  view.setUint32(4, 36 + total * 2, true);
  ascii(8, 'WAVEfmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, stream.sampleRateHz, true);
  view.setUint32(28, stream.sampleRateHz * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, 'data');
  view.setUint32(40, total * 2, true);
  let offset = 44;
  for (const chunk of stream.chunks)
    for (let i = 0; i < chunk.length; i += 1, offset += 2) view.setInt16(offset, Math.max(-1, Math.min(1, chunk[i])) * 32767, true);
  return URL.createObjectURL(new Blob([view.buffer], { type: 'audio/wav' }));
}
