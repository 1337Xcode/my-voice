/** Keeps the app in step with his toolkit profile: reads it on launch and on every profile event, writes his changes back. */
import { useEffect, useRef, useSyncExternalStore } from 'react';

import { saveServerSetting } from '@/features/teach/teachApi';
import { useSettings, type Settings } from '@/features/settings/SettingsProvider';
import { APP_ORIGIN, APP_SCOPE, choicesFromPrefs, prefsFromToolkit, scopedWrites, sharedWrites, type AppChoices, type ToolkitPrefs } from './profileMapping';
import { librarian, toolkitConfigured, watchProfile } from './toolkitClient';

export type ToolkitState = { status: 'off' | 'connecting' | 'synced' | 'error'; prefs: ToolkitPrefs; syncedAt: number | null; message: string | null };

let current: ToolkitState = { status: toolkitConfigured ? 'connecting' : 'off', prefs: {}, syncedAt: null, message: null };
const listeners = new Set<() => void>();

function setToolkit(change: Partial<ToolkitState>): void {
  current = { ...current, ...change };
  listeners.forEach((listener) => listener());
}

/** The toolkit's sync status and what the profile asks of the app (reduce motion, high contrast, ...). */
export function useToolkit(): ToolkitState {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}

const choicesOf = (settings: Settings): AppChoices => ({
  textSize: settings.textSize,
  highContrast: settings.highContrast,
  reduceMotion: settings.reduceMotion,
  speechRate: settings.speechRate,
  beforeSpeaking: settings.beforeSpeaking,
  voiceId: settings.voiceId,
});

/** Mount once inside SettingsProvider; renders nothing, and does nothing when the toolkit is not configured. */
export function ToolkitSync() {
  const { settings, loaded, update } = useSettings();
  // Read through refs: profile events arrive long after mount, and must not apply stale settings.
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const updateRef = useRef(update);
  updateRef.current = update;
  // The choices the toolkit and the app last agreed on; a difference is his own change to write back.
  const agreed = useRef<AppChoices | null>(null);

  useEffect(() => {
    if (!toolkitConfigured || !loaded) return;
    const read = async () => {
      try {
        const [profile, effective] = await Promise.all([librarian('getProfile'), librarian('effectivePreferences', [`app://${APP_ORIGIN}`, [APP_SCOPE]])]);
        const prefs = prefsFromToolkit(profile, effective);
        const mine = settingsRef.current;
        const next = choicesFromPrefs(prefs, choicesOf(mine));
        agreed.current = next;
        updateRef.current(next);
        // The voice speed lives on the server; Settings may not be open to send it.
        if (next.speechRate !== mine.speechRate) await saveServerSetting(mine, { speech_rate: next.speechRate });
        setToolkit({ status: 'synced', prefs, syncedAt: Date.now(), message: null });
      } catch (e) {
        setToolkit({ status: 'error', message: (e as Error).message });
      }
    };
    void read();
    return watchProfile(() => void read(), (message) => setToolkit({ message }));
    // Runs once settings have loaded; later reads come from profile events.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded]);

  const choices = choicesOf(settings);
  const key = JSON.stringify(choices);
  useEffect(() => {
    // Nothing to write until the first read has set what both sides agree on.
    if (!toolkitConfigured || !agreed.current) return;
    const before = agreed.current;
    const shared = sharedWrites(before, choices);
    const scoped = scopedWrites(before, choices);
    if (!shared.length && !scoped) return;
    agreed.current = choices;
    Promise.all([
      ...shared.map(([name, value]) => librarian('recordExplicitSetting', [name, value, APP_ORIGIN])),
      ...(scoped ? [librarian('recordScopedSettings', [APP_SCOPE, scoped, { writer: 'person' }])] : []),
    ])
      .then(() => setToolkit({ status: 'synced', syncedAt: Date.now(), message: null }))
      .catch((e: Error) => setToolkit({ status: 'error', message: `Not saved to your profile: ${e.message}` }));
    // key carries every choice that matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return null;
}
