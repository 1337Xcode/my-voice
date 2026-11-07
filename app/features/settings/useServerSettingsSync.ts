/** Sends the pipeline settings he changes to the server (`POST /settings`), only the changed fields, and reports a failure in place. */
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '@/features/connection/api';
import { serverSettingsOf, useSettings } from './SettingsProvider';

type ServerSettings = ReturnType<typeof serverSettingsOf>;

/** The fields of `next` that differ from `previous`. Thresholds are sent only when he edits them, never on their own. */
function changedFields(previous: ServerSettings, next: ServerSettings): Partial<ServerSettings> {
  const changed: Record<string, unknown> = {};
  for (const key of Object.keys(next) as (keyof ServerSettings)[]) if (next[key] !== previous[key] && next[key] !== undefined) changed[key] = next[key];
  return changed as Partial<ServerSettings>;
}

export function useServerSettingsSync(): { error: string | null; retry: () => void } {
  const { settings, loaded } = useSettings();
  const [error, setError] = useState<string | null>(null);
  const current = serverSettingsOf(settings);
  const key = JSON.stringify(current);
  const sent = useRef<ServerSettings | null>(null);
  const failed = useRef<Partial<ServerSettings> | null>(null);

  const send = useCallback(
    (changes: Partial<ServerSettings>) => {
      api(settings, `/settings?speaker=${settings.dev.speaker}`, { method: 'POST', body: JSON.stringify(changes) })
        .then(() => {
          failed.current = null;
          setError(null);
        })
        .catch((e: Error) => {
          failed.current = changes;
          setError(`Not saved on the server: ${e.message}`);
        });
    },
    [settings],
  );

  useEffect(() => {
    if (!loaded) return;
    // What the screen opened with is what the server already has.
    if (!sent.current) {
      sent.current = current;
      return;
    }
    const changes = changedFields(sent.current, current);
    sent.current = current;
    if (Object.keys(changes).length) send(changes);
    // key captures every field of current.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, key]);

  const retry = useCallback(() => failed.current && send(failed.current), [send]);
  return { error, retry };
}
