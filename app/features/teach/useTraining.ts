/** Retraining status: read once from `GET /train/status`, then live from the socket's `training` and `model_update` messages. */
import { useCallback, useEffect, useState } from 'react';

import { useConnection } from '@/features/connection/ConnectionProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { fetchParsed, startTraining, trainingSchema, type TrainingStatus } from './teachApi';

const RUNNING = ['queued', 'training', 'evaluating'];

/** True while a training run is under way. */
export function isTraining(status: TrainingStatus | null): boolean {
  return status !== null && RUNNING.includes(status.state);
}

/** One line for the status: the trainer's own message, with the time left when known. */
export function trainingLine(status: TrainingStatus): string {
  const message = status.message || { queued: 'Queued', training: 'Training', evaluating: 'Testing on your sentences', promoted: 'Your new model is active', not_better: 'Not better yet', failed: 'Training failed' }[status.state] || '';
  const minutes = status.eta_s ? Math.max(1, Math.round(status.eta_s / 60)) : null;
  return minutes && isTraining(status) ? `${message} · about ${minutes} min left` : message;
}

/** `onModelUpdate` runs after a new model is promoted, so screens can reload their numbers. */
export function useTraining(onModelUpdate?: () => void) {
  const { settings, loaded } = useSettings();
  const { socket } = useConnection();
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!loaded) return;
    fetchParsed(settings, '/train/status', trainingSchema)
      .then(setStatus)
      .catch(() => undefined); // The status is a nicety; the button still works without it.
    // Only the server address, token and speaker change what this reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, settings.dev.serverUrl, settings.dev.token, settings.dev.speaker]);

  useEffect(() => {
    if (!socket) return;
    return socket.onMessage((message) => {
      if (message.type === 'training') setStatus({ state: message.state, progress: message.progress, eta_s: message.eta_s, message: message.message });
      if (message.type === 'model_update') onModelUpdate?.();
      if (message.type === 'training' && ['promoted', 'not_better'].includes(message.state)) onModelUpdate?.();
    });
  }, [socket, onModelUpdate]);

  const start = useCallback(async () => {
    setStarting(true);
    setError(null);
    try {
      setStatus(await startTraining(settings));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }, [settings]);

  return { status, error, starting, running: isTraining(status), start };
}
