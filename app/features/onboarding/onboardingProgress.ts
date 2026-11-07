/** Where he is in first-run setup (spec 10), kept on the phone so every step can be skipped and resumed from Teach. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';

export const STEPS = ['welcome', 'voice', 'phrases', 'test', 'record', 'train', 'done'] as const;
export type Step = (typeof STEPS)[number];

export type OnboardingProgress = {
  step: Step;
  /** He reached the end, or chose to finish later; either way it no longer opens by itself. */
  seen: boolean;
  /** He reached Done. Until then Teach offers to continue. */
  finished: boolean;
};

const STORAGE_KEY = 'onboarding.v1';
const initial: OnboardingProgress = { step: 'welcome', seen: false, finished: false };

/** Reads the saved progress; null when setup has never been opened on this phone. */
export async function readOnboarding(): Promise<OnboardingProgress | null> {
  const raw = await AsyncStorage.getItem(STORAGE_KEY).catch(() => null);
  if (!raw) return null;
  const stored = JSON.parse(raw) as Partial<OnboardingProgress>;
  return { ...initial, ...stored, step: STEPS.includes(stored.step as Step) ? (stored.step as Step) : 'welcome' };
}

/** Saves progress as given. */
export async function writeOnboarding(progress: OnboardingProgress): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(progress)).catch(() => undefined);
}

/** The saved progress for a screen, with a setter that saves every change. */
export function useOnboardingProgress() {
  const [progress, setProgress] = useState<OnboardingProgress | null>(null);

  useEffect(() => {
    readOnboarding().then((stored) => setProgress(stored ?? initial));
  }, []);

  const save = useCallback((change: Partial<OnboardingProgress>) => {
    setProgress((current) => {
      const next = { ...(current ?? initial), ...change };
      void writeOnboarding(next);
      return next;
    });
  }, []);

  return { progress, save };
}
