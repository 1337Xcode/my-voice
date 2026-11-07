/**
 * The lips experiment on one screen (EXP X0): asks the server for lips mode, runs the camera while the screen is open
 * and visible, and keeps the server's audio-to-device clock current. Everything stops when the screen closes.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { useConnection } from '@/features/connection/ConnectionProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { useExperimentChoices } from '../store';
import { LipCamera, type LipStatus } from './LipCamera';

// The server maps audio samples to the device clock from these (EXP-SPEC 4.3).
const AUDIO_CLOCK_EVERY_MS = 1_000;

export type LipsPhase = 'needs_consent' | 'connecting' | 'starting' | 'on' | 'paused' | 'error';

type Session = { id: string; connection: unknown };

export function useLips({ handsFree = false }: { handsFree?: boolean } = {}) {
  const { socket, status: connection, ready } = useConnection();
  const { settings } = useSettings();
  const { lipsCamera } = useExperimentChoices();
  // The lips session the server granted, tied to the connection it was granted on.
  const [session, setSession] = useState<Session | null>(null);
  const [cameraOn, setCameraOn] = useState<LipCamera | null>(null);
  const [status, setStatus] = useState<LipStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  const [attempt, setAttempt] = useState(0);
  const camera = useRef<LipCamera | null>(null);
  const connected = connection === 'ready' && socket !== null && ready !== null;
  const sessionId = connected && session?.connection === ready ? session.id : null;

  // Lips mode on for this server session; after a reconnect the new session is asked again.
  useEffect(() => {
    if (!lipsCamera || !connected || !socket) return;
    const grantedOn = ready;
    const off = socket.onMessage((message) => {
      if (message.type !== 'lips_mode') return;
      if (message.on && message.session_id) setSession({ id: message.session_id, connection: grantedOn });
      else setError(message.reason ?? 'Lip reading is not available on the server right now.');
    });
    socket.send({ type: 'lips_mode', on: true, hands_free: handsFree });
    return () => {
      off();
      socket.send({ type: 'lips_mode', on: false });
    };
  }, [attempt, connected, handsFree, lipsCamera, ready, socket]);

  // The camera stops when the page is hidden (another app, the lock screen) and starts again when it comes back.
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);

  useEffect(() => {
    if (!sessionId || !lipsCamera || !visible) return;
    let cancelled = false;
    const lips = new LipCamera({
      serverUrl: settings.dev.serverUrl,
      token: settings.dev.token,
      sessionId,
      onStatus: (next) => !cancelled && setStatus(next),
      onError: (message) => !cancelled && setError(message),
    });
    camera.current = lips;
    lips
      .start()
      .then(() => !cancelled && setCameraOn(lips))
      .catch((startError: Error) => {
        lips.stop();
        if (!cancelled) setError(startError.message);
      });
    return () => {
      cancelled = true;
      lips.stop();
      camera.current = null;
      setCameraOn(null);
      setStatus(null);
    };
  }, [attempt, lipsCamera, sessionId, settings.dev.serverUrl, settings.dev.token, visible]);

  const phase: LipsPhase = !lipsCamera ? 'needs_consent' : error ? 'error' : !sessionId ? 'connecting' : !visible ? 'paused' : cameraOn ? 'on' : 'starting';

  // Once a second: how many samples the app has sent, and when (device clock).
  useEffect(() => {
    if (phase !== 'on' || !socket) return;
    const timer = setInterval(() => socket.send({ type: 'audio_clock', samples: socket.audioSamplesSent, device_ms: performance.timeOrigin + performance.now() }), AUDIO_CLOCK_EVERY_MS);
    return () => clearInterval(timer);
  }, [phase, socket]);

  const retry = useCallback(() => {
    setError(null);
    setAttempt((n) => n + 1);
  }, []);

  return { phase, status, error, retry, camera };
}
