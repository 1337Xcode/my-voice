/** Opens first-run setup on a phone that has never seen it, unless the server already holds his recordings. */
import { router } from 'expo-router';
import { useEffect, useRef } from 'react';

import { useConnection } from '@/features/connection/ConnectionProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { fetchParsed, stateSchema } from '@/features/teach/teachApi';
import { readOnboarding, writeOnboarding } from './onboardingProgress';

export function FirstRunRedirect() {
  const { settings, loaded } = useSettings();
  const { status } = useConnection();
  const checked = useRef(false);

  useEffect(() => {
    // Wait until the server accepted his access code; before that /state can only fail.
    if (!loaded || status !== 'ready' || checked.current) return;
    checked.current = true;
    (async () => {
      if (await readOnboarding()) return;
      // Unknown when the server can't be reached; ask again on the next launch rather than guess.
      const state = await fetchParsed(settings, '/state', stateSchema).catch(() => null);
      if (!state) return;
      // A speaker with recordings already set up on another phone; don't make him start over.
      if (state.clips.total > 0) {
        await writeOnboarding({ step: 'done', seen: true, finished: true });
        return;
      }
      router.push('/onboarding');
    })();
  }, [loaded, settings, status]);

  return null;
}
