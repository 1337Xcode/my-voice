/** His preferences and the hidden developer settings, stored on the phone and shared app-wide. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import type { TextSize } from '@/theme';

export type Speaker = 'S1' | 'P1';
export type BeforeSpeaking = 'speak' | 'check';

export type Settings = {
  textSize: TextSize;
  beforeSpeaking: BeforeSpeaking;
  /** His chosen ElevenLabs voice; null until he picks one (the server's default is used). */
  voiceId: string | null;
  /** The chosen microphone; null for the system default. */
  micDeviceId: string | null;
  /** AAA text contrast (spec 11.10). */
  highContrast: boolean;
  /** Motion off even when the system allows it (spec 11.10). */
  reduceMotion: boolean;
  /** How fast his voice speaks, 0.7 to 1.2 (server side). */
  speechRate: number;
  dev: {
    serverUrl: string;
    token: string;
    speaker: Speaker;
    speakThreshold: number;
    pickThreshold: number;
    endpointSilenceMs: number;
    partials: boolean;
    /** True once someone picked the speaker in the developer panel; until then the build's default applies. */
    speakerChosen?: boolean;
  };
};

const STORAGE_KEY = 'settings.v1';

export const defaultSettings: Settings = {
  textSize: 'large',
  beforeSpeaking: 'speak',
  voiceId: null,
  micDeviceId: null,
  highContrast: false,
  reduceMotion: false,
  speechRate: 1,
  dev: {
    serverUrl: process.env.EXPO_PUBLIC_SERVER_URL ?? '',
    token: process.env.EXPO_PUBLIC_APP_TOKEN ?? '',
    // The public build is his (S1); local development defaults to the developer's test voice (P1).
    speaker: process.env.EXPO_PUBLIC_DEFAULT_SPEAKER === 'S1' ? 'S1' : 'P1',
    speakThreshold: 0.85,
    pickThreshold: 0.55,
    endpointSilenceMs: 900,
    partials: false,
  },
};

/** The pipeline settings the server keeps (spec 12.2 `POST /settings`), with its field names. */
export function serverSettingsOf(settings: Settings) {
  return {
    voice_id: settings.voiceId ?? undefined,
    before_speaking: settings.beforeSpeaking,
    speech_rate: settings.speechRate,
    speak_threshold: settings.dev.speakThreshold,
    pick_threshold: settings.dev.pickThreshold,
    endpoint_silence_ms: settings.dev.endpointSilenceMs,
  };
}

/** What `hello` carries: only his own choices, never thresholds, which the server's calibration owns. */
export function helloSettingsOf(settings: Settings) {
  return { voice_id: settings.voiceId ?? undefined, before_speaking: settings.beforeSpeaking };
}

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
  // A speaker saved before this build's default existed (e.g. the developer's P1 on his phone) yields to the default.
  if (!dev.speakerChosen) dev.speaker = defaultSettings.dev.speaker;
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
