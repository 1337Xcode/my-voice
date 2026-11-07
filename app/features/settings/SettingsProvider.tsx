/** His preferences and the hidden developer settings, stored on the phone and shared app-wide. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import type { TextSize } from '@/theme';

export type Speaker = 'S1' | 'P1';
export type BeforeSpeaking = 'speak' | 'check';

export type Settings = {
  textSize: TextSize;
  beforeSpeaking: BeforeSpeaking;
  dev: {
    serverUrl: string;
    token: string;
    speaker: Speaker;
    speakThreshold: number;
    pickThreshold: number;
    endpointSilenceMs: number;
    partials: boolean;
  };
};

const STORAGE_KEY = 'settings.v1';

export const defaultSettings: Settings = {
  textSize: 'large',
  beforeSpeaking: 'speak',
  dev: {
    serverUrl: process.env.EXPO_PUBLIC_SERVER_URL ?? '',
    token: process.env.EXPO_PUBLIC_APP_TOKEN ?? '',
    speaker: 'P1',
    speakThreshold: 0.85,
    pickThreshold: 0.55,
    endpointSilenceMs: 900,
    partials: false,
  },
};

type SettingsContextValue = {
  settings: Settings;
  loaded: boolean;
  update: (change: Partial<Omit<Settings, 'dev'>>) => void;
  updateDev: (change: Partial<Settings['dev']>) => void;
};

const SettingsContext = createContext<SettingsContextValue | null>(null);

/** Merges stored settings over the defaults, so new fields get their default values. */
function mergeStored(raw: string | null): Settings {
  if (!raw) return defaultSettings;
  const stored = JSON.parse(raw) as Partial<Settings>;
  const dev = { ...defaultSettings.dev, ...stored.dev };
  // Blank developer overrides fall back to the build's public env.
  dev.serverUrl = dev.serverUrl || defaultSettings.dev.serverUrl;
  dev.token = dev.token || defaultSettings.dev.token;
  return { ...defaultSettings, ...stored, dev };
}

/** Loads settings once, then saves every change. */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => setSettings(mergeStored(raw)))
      .catch(() => setSettings(defaultSettings))
      .finally(() => setLoaded(true));
  }, []);

  const save = useCallback((next: Settings) => {
    setSettings(next);
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => undefined);
  }, []);

  const value = useMemo<SettingsContextValue>(
    () => ({
      settings,
      loaded,
      update: (change) => save({ ...settings, ...change }),
      updateDev: (change) => save({ ...settings, dev: { ...settings.dev, ...change } }),
    }),
    [settings, loaded, save],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

/** Reads and changes the settings from any screen. */
export function useSettings(): SettingsContextValue {
  const value = useContext(SettingsContext);
  if (!value) throw new Error('useSettings must be used inside SettingsProvider');
  return value;
}
