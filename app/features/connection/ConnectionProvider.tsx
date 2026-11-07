/** Shares one SpeechSocket across the app and restarts it when the server settings change. */
import Constants from 'expo-constants';
import { createContext, ReactNode, useContext, useEffect, useRef, useState } from 'react';

import { useSettings } from '@/features/settings/SettingsProvider';
import type { ReadyMessage } from './protocol';
import { ConnectionStatus, SpeechSocket } from './SpeechSocket';

type ConnectionValue = {
  socket: SpeechSocket | null;
  status: ConnectionStatus;
  ready: ReadyMessage | null;
  /** Plain-language error from the server's last `error` message, if any. */
  lastError: string | null;
};

const ConnectionContext = createContext<ConnectionValue>({ socket: null, status: 'connecting', ready: null, lastError: null });

export const clientVersion = Constants.expoConfig?.version ?? '0.0.0';

/** Owns the socket's lifetime; one per app. */
export function ConnectionProvider({ children }: { children: ReactNode }) {
  const { settings, loaded } = useSettings();
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const [value, setValue] = useState<ConnectionValue>({ socket: null, status: 'connecting', ready: null, lastError: null });
  const { serverUrl, token, speaker } = settings.dev;

  useEffect(() => {
    if (!loaded) return;
    const socket = new SpeechSocket({
      serverUrl,
      token,
      hello: () => ({
        type: 'hello',
        speaker: settingsRef.current.dev.speaker,
        client_version: clientVersion,
        settings: { before_speaking: settingsRef.current.beforeSpeaking, ...settingsRef.current.dev, token: undefined },
      }),
    });
    setValue({ socket, status: socket.status, ready: null, lastError: null });
    const offStatus = socket.onStatus((status) => setValue((v) => ({ ...v, status, ready: socket.ready })));
    const offMessage = socket.onMessage((message) => {
      if (message.type === 'error') setValue((v) => ({ ...v, lastError: String(message.message ?? '') }));
      if (message.type === 'ready') setValue((v) => ({ ...v, ready: socket.ready, lastError: null }));
    });
    socket.start();
    return () => {
      offStatus();
      offMessage();
      socket.stop();
    };
  }, [loaded, serverUrl, token, speaker]);

  return <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>;
}

/** The connection's current status, readiness and socket. */
export function useConnection(): ConnectionValue {
  return useContext(ConnectionContext);
}
