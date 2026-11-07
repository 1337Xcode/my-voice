/** Loads one server route for a screen, with loading, error and retry states. */
import { useCallback, useEffect, useState } from 'react';

import { useSettings } from '@/features/settings/SettingsProvider';
import { api } from './api';

export type ServerData<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/** Fetches `path` (with the active speaker) whenever the server settings change. */
export function useServerData<T>(path: string): ServerData<T> {
  const { settings, loaded } = useSettings();
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true });
  const [attempt, setAttempt] = useState(0);
  const separator = path.includes('?') ? '&' : '?';
  const fullPath = `${path}${separator}speaker=${settings.dev.speaker}`;

  useEffect(() => {
    if (!loaded) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    api<T>(settings, fullPath)
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error: Error) => !cancelled && setState((s) => ({ ...s, error: error.message, loading: false })));
    return () => {
      cancelled = true;
    };
    // settings is read for the URL and token only; those are in the key below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, fullPath, settings.dev.serverUrl, settings.dev.token, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
