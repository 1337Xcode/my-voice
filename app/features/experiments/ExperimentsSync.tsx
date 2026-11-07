/** Tells the server which experiments he has switched on, after every (re)connect and on every change. */
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';

import { useConnection } from '@/features/connection/ConnectionProvider';
import { canStreamVoice, unlockOnNextTap } from './realtime/streamPlayer';
import { useExperimentChoices } from './store';

/** Which experiments this server and this device can run. Both false keeps the app exactly as it was. */
export function useExperimentAvailability() {
  const { ready } = useConnection();
  const web = Platform.OS === 'web';
  return {
    realtimeVoice: Boolean(ready?.features?.realtime_voice) && web && canStreamVoice(),
    lips: Boolean(ready?.features?.lips) && web && typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia),
  };
}

/** Mounted once in the root layout; renders nothing. */
export function ExperimentsSync() {
  const { socket, status, ready } = useConnection();
  const choices = useExperimentChoices();
  const available = useExperimentAvailability();
  const streamed = choices.streamedVoice && available.realtimeVoice;
  const lastSent = useRef<string | null>(null);

  useEffect(() => {
    if (status !== 'ready' || !socket || !ready) {
      lastSent.current = null;
      return;
    }
    // Only a server that runs experiments hears about them; the core protocol is untouched otherwise.
    if (!ready.features?.realtime_voice && !ready.features?.lips) return;
    const message = { type: 'experiments', realtime_voice: streamed };
    const key = `${ready.speaker}:${JSON.stringify(message)}`;
    if (lastSent.current === key) return;
    if (socket.send(message)) lastSent.current = key;
  }, [ready, socket, status, streamed]);

  // Streamed voice plays through Web Audio, which a tap must unlock (iOS Safari).
  useEffect(() => (streamed ? unlockOnNextTap() : undefined), [streamed]);

  return null;
}
