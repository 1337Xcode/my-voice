/** The Teach prompt queue: the server's next prompt (`GET /teach/next`), Keep (upload), and Skip for phrase prompts. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { z } from 'zod';

import { useSettings } from '@/features/settings/SettingsProvider';
import { fetchParsed, nextSchema, uploadClip, type TeachProgress, type TeachPrompt } from './teachApi';

const bankSchema = z.object({ phrases: z.array(z.object({ id: z.string(), text: z.string(), template_clip_ids: z.array(z.string()).optional() })) });
type BankPhrase = z.infer<typeof bankSchema>['phrases'][number];

/**
 * The prompt to show once some phrases are skipped. The server always returns the first phrase that still
 * needs a recording, so phrases before it are complete; after it, one template means the next take is the
 * held-out repeat (test), none means the first take (train), and two or more means it is done.
 */
export function promptAfterSkips(server: TeachPrompt, bank: BankPhrase[], skipped: string[]): TeachPrompt | null {
  if (server.kind !== 'phrase' || !server.phrase_id || !skipped.includes(server.phrase_id)) return server;
  const start = bank.findIndex((p) => p.id === server.phrase_id);
  for (const phrase of bank.slice(Math.max(0, start))) {
    if (skipped.includes(phrase.id)) continue;
    const templates = phrase.template_clip_ids?.length ?? 0;
    if (templates >= 2) continue;
    return { kind: 'phrase', text: phrase.text, phrase_id: phrase.id, split: templates === 0 ? 'train' : 'test', condition: 'quiet' };
  }
  return null;
}

export function usePromptQueue() {
  const { settings, loaded } = useSettings();
  const [server, setServer] = useState<TeachPrompt | null>(null);
  const [progress, setProgress] = useState<TeachProgress | null>(null);
  const [bank, setBank] = useState<BankPhrase[]>([]);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!loaded) return;
    let cancelled = false;
    setLoading(true);
    const load = () => Promise.all([fetchParsed(settings, '/teach/next', nextSchema), fetchParsed(settings, '/phrases', bankSchema)]);
    // The server can drop a read while another request reloads its storage; one quiet retry covers that.
    load()
      .catch(() => new Promise((resolve) => setTimeout(resolve, 1_500)).then(load))
      .then(([next, phrases]) => {
        if (cancelled) return;
        setServer(next.prompt);
        setProgress(next.progress);
        setBank(phrases.phrases);
        setError(null);
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // Only the server address, token and speaker change what this loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, settings.dev.serverUrl, settings.dev.token, settings.dev.speaker, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const prompt = useMemo(() => (server ? promptAfterSkips(server, bank, skipped) : null), [server, bank, skipped]);

  /** Uploads the take for the current prompt, then loads the next one. */
  const keep = useCallback(
    async (wav: Uint8Array) => {
      if (!prompt || prompt.kind === 'done') return;
      const saved = await uploadClip(settings, { wav, text: prompt.text, phraseId: prompt.phrase_id, promptId: prompt.prompt_id, split: prompt.split, condition: prompt.condition });
      if (saved) setProgress(saved);
      reload();
    },
    [prompt, settings, reload],
  );

  /** Skips a phrase for this visit; an everyday sentence is simply replaced by a new one. */
  const skip = useCallback(() => {
    if (prompt?.phrase_id) setSkipped((list) => [...list, prompt.phrase_id as string]);
    else if (prompt?.kind === 'like_yours') reload();
  }, [prompt, reload]);

  // Phrases before the server's current one are complete (it returns the first that needs a take).
  const phrasesDone = server?.kind === 'phrase' ? Math.max(0, bank.findIndex((p) => p.id === server.phrase_id)) : bank.length;
  const position = prompt?.phrase_id ? { index: bank.findIndex((p) => p.id === prompt.phrase_id) + 1, of: bank.length, take: prompt.split === 'train' ? 1 : 2 } : null;

  return { prompt, progress, loading, error, reload, keep, skip, canSkip: Boolean(prompt?.phrase_id) || prompt?.kind === 'like_yours', clearSkips: () => setSkipped([]), phrasesDone, phraseCount: bank.length, position };
}
