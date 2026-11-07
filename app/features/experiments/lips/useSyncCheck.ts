/** The 10-second sync check (EXP-SPEC 4.4): he says "pa" five times; the server measures the sound-to-picture offset. */
import { useCallback, useEffect, useRef, useState } from 'react';

import { useCapture } from '@/features/audio/useCapture';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { useSettings } from '@/features/settings/SettingsProvider';

const SYNC_SECONDS = 10;
// The server answers within a second or two; past this the check has failed.
const ANSWER_TIMEOUT_MS = 20_000;

export type SyncState =
  | { kind: 'idle' }
  | { kind: 'recording'; secondsLeft: number }
  | { kind: 'measuring' }
  | { kind: 'done'; offsetMs: number }
  | { kind: 'failed'; message: string };

export function useSyncCheck() {
  const { socket } = useConnection();
  const { settings } = useSettings();
  const capture = useCapture();
  const { start: startCapture, stop: stopCapture } = capture;
  const [state, setState] = useState<SyncState>({ kind: 'idle' });
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => clear, []);

  const run = useCallback(async () => {
    if (!socket) return setState({ kind: 'failed', message: 'No connection to the speech server.' });
    clear();
    const turnId = `sync-${Date.now().toString(36)}`;
    const off = socket.onMessage((message) => {
      if (message.type === 'lips_setup' && message.step === 'sync') {
        off();
        clear();
        setState(message.ok && message.offset_ms != null ? { kind: 'done', offsetMs: message.offset_ms } : { kind: 'failed', message: message.reason ?? 'The sync check failed. Try again.' });
      }
    });
    socket.send({ type: 'start_turn', turn_id: turnId, mode: 'lips_sync' });
    try {
      await startCapture((frame) => socket.sendAudio(frame), settings.micDeviceId);
    } catch (error) {
      off();
      socket.send({ type: 'cancel_turn', turn_id: turnId });
      return setState({ kind: 'failed', message: (error as Error).message });
    }
    for (let left = SYNC_SECONDS; left > 0; left -= 1) timers.current.push(setTimeout(() => setState({ kind: 'recording', secondsLeft: left }), (SYNC_SECONDS - left) * 1000));
    timers.current.push(
      setTimeout(async () => {
        setState({ kind: 'measuring' });
        await stopCapture();
        socket.send({ type: 'end_turn', turn_id: turnId });
        timers.current.push(
          setTimeout(() => {
            off();
            setState({ kind: 'failed', message: "The server didn't answer. Try again." });
          }, ANSWER_TIMEOUT_MS),
        );
      }, SYNC_SECONDS * 1000),
    );
  }, [settings.micDeviceId, socket, startCapture, stopCapture]);

  return { state, run };
}
