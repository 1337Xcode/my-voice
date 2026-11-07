/** Live microphone capture: 16 kHz mono through @siteed/audio-studio, sent as 100 ms PCM frames, with a level meter. */
import { useAudioRecorder, type AudioDataEvent } from '@siteed/audio-studio';
import { useCallback, useMemo, useRef, useState } from 'react';

import { FrameAssembler, isNoisy, levelOf, SAMPLE_RATE_HZ, toFloat32 } from './pcm';
import { MicProcessing, withMicProcessing } from './micProcessing';
import { isVoicePlaying } from './playback';

// How many recent 100 ms levels the meter keeps: 3 seconds.
const LEVEL_HISTORY = 30;

export type Capture = {
  /** Recent input levels (0 to 1), oldest first, one per 100 ms. */
  levels: number[];
  /** True when the room between his words is loud. */
  noisy: boolean;
  /** Starts the microphone and calls `onFrame` with each 3,200-byte frame. Throws a plain-language error. `raw` (no browser processing) unless told otherwise. */
  start: (onFrame: (frame: ArrayBuffer) => void, deviceId?: string | null, processing?: MicProcessing) => Promise<void>;
  /** Stops the microphone, sending the last partial frame first. */
  stop: () => Promise<void>;
};

/** Turns the recorder's failure into a sentence he can act on. */
function captureError(error: unknown): Error {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  if (/denied|permission|notallowed/i.test(text)) return new Error('Microphone access is off. Allow it for My Voice, then try again.');
  if (/notfound|no device|overconstrained/i.test(text)) return new Error('No microphone was found. Connect one and try again.');
  return new Error('The microphone could not start. Try again.');
}

export function useCapture(): Capture {
  const { startRecording, stopRecording } = useAudioRecorder();
  const [levels, setLevels] = useState<number[]>([]);
  const assembler = useRef(new FrameAssembler());
  const onFrameRef = useRef<((frame: ArrayBuffer) => void) | null>(null);
  const activeRef = useRef(false);

  const handleAudio = useCallback(async (event: AudioDataEvent) => {
    const send = onFrameRef.current;
    if (!activeRef.current || !send) return;
    const samples = toFloat32(event.data);
    // Half duplex: while our own voice plays, the recogniser must not hear it.
    if (isVoicePlaying()) return;
    for (const frame of assembler.current.push(samples)) send(frame);
    const level = levelOf(samples);
    setLevels((previous) => [...previous.slice(-(LEVEL_HISTORY - 1)), level]);
  }, []);

  const start = useCallback(
    async (onFrame: (frame: ArrayBuffer) => void, deviceId?: string | null, processing: MicProcessing = 'raw') => {
      assembler.current = new FrameAssembler();
      onFrameRef.current = onFrame;
      activeRef.current = true;
      setLevels([]);
      try {
        await withMicProcessing(processing, () => startRecording({
          sampleRate: SAMPLE_RATE_HZ,
          channels: 1,
          encoding: 'pcm_32bit',
          streamFormat: 'float32',
          interval: 100,
          deviceId: deviceId ?? undefined,
          // Stream only: no file is kept on the phone.
          output: { primary: { enabled: false } },
          onAudioStream: handleAudio,
        }));
      } catch (error) {
        activeRef.current = false;
        onFrameRef.current = null;
        throw captureError(error);
      }
    },
    [startRecording, handleAudio],
  );

  const stop = useCallback(async () => {
    if (!activeRef.current) return;
    activeRef.current = false;
    const last = assembler.current.flush();
    if (last && onFrameRef.current) onFrameRef.current(last);
    onFrameRef.current = null;
    await stopRecording().catch(() => null);
  }, [stopRecording]);

  return useMemo(() => ({ levels, noisy: isNoisy(levels), start, stop }), [levels, start, stop]);
}
