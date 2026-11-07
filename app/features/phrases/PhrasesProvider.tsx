/** His phrase bank: loaded from the server, kept on the phone for offline use, and spoken in one tap. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { z } from 'zod';

import { mp3Uri, playUri, prepareVoice, speakWithPhoneVoice } from '@/features/audio/playback';
import { requestPhraseAudio, requestTypedAudio } from '@/features/audio/serverVoice';
import { api } from '@/features/connection/api';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { APP_FORMAT, downloadMissing, storedClipUri } from './phraseAudio';

const phraseSchema = z.object({
  id: z.string(),
  text: z.string(),
  category: z.string(),
  order: z.number(),
  pinned: z.boolean().optional(),
  tts: z.record(z.string(), z.string()).optional(),
  uses: z.number().optional(),
});
const bankSchema = z.object({ phrases: z.array(phraseSchema) });

export type Phrase = z.infer<typeof phraseSchema>;

const BANK_KEY = 'phrases.v1';
const USES_KEY = 'phraseUses.v1';

/** Shown first everywhere, so he can explain the pause before anyone gets impatient. */
const PATIENCE_TEXT = 'My app speaks for me. Thanks for your patience.';
const patiencePhrase: Phrase = { id: 'local-patience', text: PATIENCE_TEXT, category: 'Pinned', order: -1, pinned: true };

type PhrasesValue = {
  phrases: Phrase[];
  /** Up to `count` phrases, pinned first, then by how often he uses them. */
  mostUsed: (count: number) => Phrase[];
  categories: string[];
  loading: boolean;
  error: string | null;
  reload: () => void;
  /** Plays the phrase in his voice (or the phone's voice when offline and not stored); resolves with the clip's URI (null for the phone's voice) once sound starts. */
  say: (phrase: Phrase) => Promise<string | null>;
};

const PhrasesContext = createContext<PhrasesValue | null>(null);

/** Pinned phrases first, then the bank in its own order; adds the patience phrase if the bank lacks it. */
function arrange(bank: Phrase[]): Phrase[] {
  const hasPatience = bank.some((phrase) => phrase.text === PATIENCE_TEXT);
  const all = hasPatience ? bank : [patiencePhrase, ...bank];
  return [...all.filter((p) => p.pinned), ...all.filter((p) => !p.pinned)];
}

export function PhrasesProvider({ children, enabled = true }: { children: ReactNode; enabled?: boolean }) {
  const { settings, loaded } = useSettings();
  const { socket, status, ready } = useConnection();
  const [bank, setBank] = useState<Phrase[]>([]);
  const [uses, setUses] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const voiceKey = `${settings.voiceId ?? ready?.voice_id ?? ''}:${APP_FORMAT}`;

  // The copy on the phone first, so phrases work offline from the first frame.
  useEffect(() => {
    prepareVoice();
    AsyncStorage.multiGet([BANK_KEY, USES_KEY])
      .then(([[, storedBank], [, storedUses]]) => {
        const parsed = bankSchema.safeParse(storedBank ? JSON.parse(storedBank) : null);
        if (parsed.success) setBank(parsed.data.phrases);
        if (storedUses) setUses(JSON.parse(storedUses) as Record<string, number>);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!loaded || !enabled) return;
    let cancelled = false;
    setLoading(true);
    api<unknown>(settings, `/phrases?speaker=${settings.dev.speaker}`)
      .then((body) => {
        const parsed = bankSchema.safeParse(body);
        if (!parsed.success) throw new Error('The phrase list from the server was not readable.');
        if (cancelled) return;
        setBank(parsed.data.phrases);
        setError(null);
        void AsyncStorage.setItem(BANK_KEY, JSON.stringify(parsed.data));
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // Only the server address, token and speaker change what this loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, enabled, settings.dev.serverUrl, settings.dev.token, settings.dev.speaker, attempt]);

  // Ask the server to make any missing clips in his current voice (`POST /phrases/cache`), once per voice, then reload.
  const cacheAsked = useRef<string | null>(null);
  useEffect(() => {
    const voice = voiceKey.split(':')[0];
    const missing = bank.some((phrase) => !phrase.tts?.[voiceKey]);
    if (!enabled || status !== 'ready' || !voice || !bank.length || !missing || cacheAsked.current === voiceKey) return;
    cacheAsked.current = voiceKey;
    const body = JSON.stringify({ voice_id: voice });
    api(settings, `/phrases/cache?speaker=${settings.dev.speaker}`, { method: 'POST', body })
      .then(() => setAttempt((n) => n + 1))
      .catch(() => undefined); // Phrases still play through the server; only offline playback waits for the clips.
    // settings is only read for the address and token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bank, voiceKey, status, enabled]);

  // Keep every phrase's clip in his current voice on the device.
  useEffect(() => {
    const files = bank.map((phrase) => phrase.tts?.[voiceKey]).filter((file): file is string => Boolean(file));
    if (files.length && status === 'ready') void downloadMissing(settings, files);
    // settings is only read for the address and token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bank, voiceKey, status]);

  const say = useCallback(
    async (phrase: Phrase) => {
      const next = { ...uses, [phrase.id]: (uses[phrase.id] ?? 0) + 1 };
      setUses(next);
      void AsyncStorage.setItem(USES_KEY, JSON.stringify(next));
      const file = phrase.tts?.[voiceKey];
      const stored = file ? await storedClipUri(file) : null;
      if (stored) {
        await playUri(stored);
        return stored;
      }
      if (socket && status === 'ready') {
        const audio = phrase.id === patiencePhrase.id ? await requestTypedAudio(socket, phrase.text) : await requestPhraseAudio(socket, phrase.id);
        const uri = await mp3Uri(audio.data);
        await playUri(uri);
        return uri;
      }
      await speakWithPhoneVoice(phrase.text);
      return null;
    },
    [uses, voiceKey, socket, status],
  );

  const value = useMemo<PhrasesValue>(() => {
    const phrases = arrange(bank);
    const score = (p: Phrase) => Math.max(uses[p.id] ?? 0, p.uses ?? 0);
    return {
      phrases,
      mostUsed: (count) => {
        const pinned = phrases.filter((p) => p.pinned);
        const rest = phrases.filter((p) => !p.pinned).sort((a, b) => score(b) - score(a) || a.order - b.order);
        return [...pinned, ...rest].slice(0, count);
      },
      categories: [...new Set(bank.map((p) => p.category))],
      loading,
      error,
      reload: () => setAttempt((n) => n + 1),
      say,
    };
  }, [bank, uses, loading, error, say]);

  return <PhrasesContext.Provider value={value}>{children}</PhrasesContext.Provider>;
}

/** His phrases and the one-tap speaker, from any screen. */
export function usePhrases(): PhrasesValue {
  const value = useContext(PhrasesContext);
  if (!value) throw new Error('usePhrases must be used inside PhrasesProvider');
  return value;
}
