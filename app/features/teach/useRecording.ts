/** Records one Teach prompt through the same capture path as Talk, keeping it in memory as a WAV to play back, keep or redo. */
import { useCallback, useEffect, useRef, useState } from 'react';

import { playUri, stopVoice } from '@/features/audio/playback';
import { useCapture } from '@/features/audio/useCapture';
import { useSettings } from '@/features/settings/SettingsProvider';
import { buzz } from '@/features/talk/haptics';
import { secondsOf, wavFromFrames, wavUri } from './wav';

// A prompt is one sentence; past this the recording stops by itself.
const MAX_SECONDS = 20;
// Under this there is nothing the server can learn from (it rejects under 0.25 s of speech).
const MIN_SECONDS = 0.6;

export type RecordingState = { kind: 'ready' } | { kind: 'recording'; seconds: number } | { kind: 'recorded'; wav: Uint8Array; seconds: number };

export function useRecording() {
  const { settings } = useSettings();
  const capture = useCapture();
  const { start: startCapture, stop: stopCapture } = capture;
  const [state, setState] = useState<RecordingState>({ kind: 'ready' });
  const [error, setError] = useState<string | null>(null);
  const frames = useRef<ArrayBuffer[]>([]);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTicker = () => {
    if (ticker.current) clearInterval(ticker.current);
    ticker.current = null;
  };

  const stop = useCallback(async () => {
    clearTicker();
    await stopCapture();
    const seconds = secondsOf(frames.current);
    if (seconds < MIN_SECONDS) {
      setState({ kind: 'ready' });
      setError("That was too short to hear anything. Tap Record, then say the sentence.");
      return;
    }
    setState({ kind: 'recorded', wav: wavFromFrames(frames.current), seconds });
  }, [stopCapture]);

  const stopRef = useRef(stop);
  stopRef.current = stop;

  const start = useCallback(async () => {
    stopVoice();
    setError(null);
    frames.current = [];
    try {
      await startCapture((frame) => frames.current.push(frame), settings.micDeviceId);
    } catch (e) {
      buzz('error');
      setError((e as Error).message);
      return;
    }
    buzz('listen');
    setState({ kind: 'recording', seconds: 0 });
    ticker.current = setInterval(() => {
      const seconds = secondsOf(frames.current);
      setState({ kind: 'recording', seconds });
      if (seconds >= MAX_SECONDS) void stopRef.current();
    }, 250);
  }, [startCapture, settings.micDeviceId]);

  const play = useCallback(async () => {
    if (state.kind !== 'recorded') return;
    setError(null);
    try {
      await playUri(await wavUri(state.wav));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [state]);

  /** Back to ready, dropping the take (Redo, or after Keep). */
  const reset = useCallback(() => {
    stopVoice();
    setError(null);
    setState({ kind: 'ready' });
  }, []);

  // Never leave the microphone on when the card goes away.
  useEffect(
    () => () => {
      clearTicker();
      void stopCapture();
    },
    [stopCapture],
  );

  return { state, error, setError, levels: capture.levels, start, stop, play, reset };
}

export type Recording = ReturnType<typeof useRecording>;
