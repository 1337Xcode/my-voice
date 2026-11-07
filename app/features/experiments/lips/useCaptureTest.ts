/**
 * The coexistence test (EXP-SPEC 4.5): camera with landmarks, the microphone streaming and his voice playing, all at
 * once, for one or ten minutes; the measurements go to the server, which says whether X0's target is met.
 */
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react';
import { z } from 'zod';

import { mp3Uri, onVoicePlaying, playUri, stopVoice } from '@/features/audio/playback';
import { FRAME_SAMPLES } from '@/features/audio/pcm';
import { requestPhraseAudio } from '@/features/audio/serverVoice';
import { useCapture } from '@/features/audio/useCapture';
import { api } from '@/features/connection/api';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import type { LipCamera } from './LipCamera';

// A saved phrase plays this often during the test, so the voice and the microphone overlap with the camera.
const VOICE_EVERY_MS = 20_000;
const VOICE_PHRASE = 'p02';
// Frames come every 100 ms; a longer silence while no voice is playing is a dropout.
const MIC_GAP_MS = 400;
// Half duplex drops frames while the voice plays; the first frame after it may take this long.
const AFTER_VOICE_MS = 600;

const verdictSchema = z.object({ seconds: z.number(), fps_median: z.number().nullable(), seconds_at_24_pct: z.number(), stalls: z.number(), mic_gaps: z.number(), mic_rate_hz: z.number().nullable(), met: z.boolean() });
export type CaptureVerdict = z.infer<typeof verdictSchema>;

export type CaptureTestState =
  | { kind: 'idle' }
  | { kind: 'running'; elapsedS: number; totalS: number; fps: number; micOk: boolean }
  | { kind: 'saving' }
  | { kind: 'done'; verdict: CaptureVerdict }
  | { kind: 'failed'; message: string };

/** Microphone bookkeeping: frames, gaps outside playback, and listening time (to work out the delivered rate). */
class MicMeter {
  frames = 0;
  gaps = 0;
  private lastFrameAt = 0;
  private listeningMs = 0;
  private listeningSince: number | null = performance.now();
  private voiceEndedAt = 0;

  frame(): void {
    const now = performance.now();
    if (this.lastFrameAt && this.listeningSince !== null && now - this.lastFrameAt > MIC_GAP_MS && now - this.voiceEndedAt > AFTER_VOICE_MS) this.gaps += 1;
    this.lastFrameAt = now;
    this.frames += 1;
  }

  voice(playing: boolean): void {
    const now = performance.now();
    if (playing && this.listeningSince !== null) {
      this.listeningMs += now - this.listeningSince;
      this.listeningSince = null;
    } else if (!playing && this.listeningSince === null) {
      this.listeningSince = now;
      this.voiceEndedAt = now;
      this.lastFrameAt = 0;
    }
  }

  /** Samples delivered per second of listening; 16000 when the microphone runs at the rate it should. */
  rateHz(): number | null {
    const listening = this.listeningMs + (this.listeningSince !== null ? performance.now() - this.listeningSince : 0);
    return listening > 5_000 ? Math.round((this.frames * FRAME_SAMPLES) / (listening / 1000)) : null;
  }
}

export function useCaptureTest(camera: MutableRefObject<LipCamera | null>) {
  const { socket } = useConnection();
  const { settings } = useSettings();
  const { start: startCapture, stop: stopCapture } = useCapture();
  const [state, setState] = useState<CaptureTestState>({ kind: 'idle' });
  const stopRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => () => void stopRef.current?.(), []);

  const run = useCallback(
    async (minutes: number) => {
      const lips = camera.current;
      if (!socket || !lips) return setState({ kind: 'failed', message: 'Wait for the camera to be ready, then try again.' });
      const totalS = minutes * 60;
      const mic = new MicMeter();
      const startStats = lips.captureStats();
      let plays = 0;
      try {
        // The frames go to the server as they would in a turn; outside a turn it counts and drops them.
        await startCapture((frame) => {
          mic.frame();
          socket.sendAudio(frame);
        }, settings.micDeviceId);
      } catch (error) {
        return setState({ kind: 'failed', message: (error as Error).message });
      }
      const offVoice = onVoicePlaying((playing) => mic.voice(playing));
      const speak = () =>
        void requestPhraseAudio(socket, VOICE_PHRASE)
          .then((audio) => mp3Uri(audio.data))
          .then(playUri)
          .then(() => (plays += 1))
          .catch(() => undefined);
      const voiceTimer = setInterval(speak, VOICE_EVERY_MS);
      const started = Date.now();
      const tick = setInterval(() => {
        const elapsedS = Math.floor((Date.now() - started) / 1000);
        setState({ kind: 'running', elapsedS, totalS, fps: lips.captureStats().fpsPerSecond.at(-1) ?? 0, micOk: mic.gaps === 0 });
        if (elapsedS >= totalS) void finish();
      }, 1000);
      setState({ kind: 'running', elapsedS: 0, totalS, fps: 0, micOk: true });

      const finish = async () => {
        stopRef.current = null;
        clearInterval(tick);
        clearInterval(voiceTimer);
        offVoice();
        stopVoice();
        await stopCapture();
        setState({ kind: 'saving' });
        const end = lips.captureStats();
        const report = {
          seconds: Math.floor((Date.now() - started) / 1000),
          frames: end.frames - startStats.frames,
          face_frames: end.faceFrames - startStats.faceFrames,
          fps_per_second: end.fpsPerSecond.slice(startStats.fpsPerSecond.length + 1),
          stalls: end.stalls - startStats.stalls,
          dropped: end.dropped - startStats.dropped,
          detect_ms_median: end.detectMsMedian,
          jpeg_bytes_mean: end.jpegBytesMean,
          mic_frames: mic.frames,
          mic_gaps: mic.gaps,
          mic_rate_hz: mic.rateHz(),
          voice_plays: plays,
        };
        try {
          const verdict = await api<unknown>(settings, `/lips/capture_report?speaker=${settings.dev.speaker}`, { method: 'POST', body: JSON.stringify(report), headers: { 'Content-Type': 'application/json' } });
          setState({ kind: 'done', verdict: verdictSchema.parse(verdict) });
        } catch (error) {
          setState({ kind: 'failed', message: (error as Error).message });
        }
      };
      stopRef.current = finish;
    },
    [camera, settings, socket, startCapture, stopCapture],
  );

  /** Ends a running test early; its measurements are still saved. */
  const stop = useCallback(() => void stopRef.current?.(), []);

  return { state, run, stop };
}
