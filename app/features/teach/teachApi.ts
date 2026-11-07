/** The Teach, Review, training and Results routes, each validated with zod before a screen uses it. */
import { fetch as expoFetch } from 'expo/fetch';
import { File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';
import { z } from 'zod';

import { api, ApiError } from '@/features/connection/api';
import type { Settings } from '@/features/settings/SettingsProvider';

const score = z.object({ words_understood: z.number(), n: z.number() }).nullable().optional();

export const stateSchema = z.object({
  model_version: z.string(),
  registry: z
    .object({
      active: z.string().nullable().optional(),
      versions: z.record(z.string(), z.object({ version: z.number().optional(), train_clips: z.number().optional() }).passthrough()).optional(),
    })
    .passthrough()
    .nullable()
    .optional(),
  clips: z.object({ total: z.number(), train: z.number(), test: z.number() }),
  review_count: z.number(),
  settings: z.object({ learn_from_conversations: z.boolean().optional() }).passthrough().optional(),
});
export type ServerState = z.infer<typeof stateSchema>;

const progressSchema = z.object({ today: z.number(), minutes: z.number(), total: z.number() });
export type TeachProgress = z.infer<typeof progressSchema>;

export const promptSchema = z.object({
  // After the phrases and Harvard lists the server writes everyday sentences (`like_yours`); `done` is kept for older servers.
  kind: z.enum(['phrase', 'harvard', 'like_yours', 'done']),
  text: z.string(),
  phrase_id: z.string().nullable().optional(),
  prompt_id: z.string().nullable().optional(),
  split: z.enum(['train', 'test']),
  condition: z.enum(['quiet', 'noisy']),
});
export type TeachPrompt = z.infer<typeof promptSchema>;

export const nextSchema = z.object({ prompt: promptSchema, progress: progressSchema });

export const reviewSchema = z.object({
  items: z.array(z.object({ turn_id: z.string(), clip_id: z.string(), text: z.string(), created_at: z.number().nullable().optional(), duration_s: z.number().nullable().optional() })),
});
export type ReviewItem = z.infer<typeof reviewSchema>['items'][number];

export const testSentencesSchema = z.object({ sentences: z.array(z.object({ id: z.string(), text: z.string(), recorded: z.boolean() })) });
export type TestSentence = z.infer<typeof testSentencesSchema>['sentences'][number];

const cell = z.object({ words_understood: z.number(), n: z.number() }).nullable();
const timing = z.object({ median: z.number().nullable(), p95: z.number().nullable(), n: z.number() });
const calibrationSchema = z.object({
  speak_threshold: z.number().nullable().optional(),
  curve: z.array(z.object({ threshold: z.number(), spoken: z.number().optional(), wrong_spoken_rate: z.number().nullable().optional(), ask_rate: z.number().nullable().optional() })).optional(),
  n: z.number().optional(),
});

export const resultsSchema = z.object({
  headline: z.array(z.object({ system: z.string(), kind: z.string(), version: z.string().optional(), quiet: cell.optional(), babble_5db: cell.optional() })),
  learning: z.array(z.object({ version: z.string(), quiet: score, babble_5db: score })),
  live: z.object({
    turns: z.number(),
    ms_end_to_text: timing,
    ms_end_to_audio: timing,
    ask_rate: z.number().nullable(),
    wrong_spoken_rate: z.number().nullable(),
    correction_rate: z.number().nullable().optional(),
  }),
  calibration: z.record(z.string(), calibrationSchema),
  test_set: z.object({ clips: z.number(), conditions: z.record(z.string(), z.number()) }),
  footnote: z.string(),
});
export type Results = z.infer<typeof resultsSchema>;
export type HeadlineRow = Results['headline'][number];

export const trainingSchema = z.object({
  state: z.string(),
  progress: z.number().nullable().optional(),
  eta_s: z.number().nullable().optional(),
  message: z.string().nullable().optional(),
});
export type TrainingStatus = z.infer<typeof trainingSchema>;

/** The path with the active speaker added. */
function withSpeaker(settings: Settings, path: string): string {
  return `${path}${path.includes('?') ? '&' : '?'}speaker=${settings.dev.speaker}`;
}

/** Calls a route and validates its body; a malformed body becomes a plain error. */
export async function fetchParsed<T>(settings: Settings, path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const parsed = schema.safeParse(await api<unknown>(settings, withSpeaker(settings, path), init));
  if (!parsed.success) throw new ApiError('The speech server sent something the app could not read. Try again.');
  return parsed.data;
}

/** His verdict on one everyday turn in Review. */
export function sendReview(settings: Settings, turnId: string, action: 'approve' | 'reject' | 'edit', text?: string): Promise<unknown> {
  return api(settings, withSpeaker(settings, `/review/${encodeURIComponent(turnId)}`), { method: 'POST', body: JSON.stringify({ action, text }) });
}

/** Starts retraining (Improve now); returns the first status. */
export function startTraining(settings: Settings): Promise<TrainingStatus> {
  return fetchParsed(settings, '/train', trainingSchema, { method: 'POST' });
}

/** Saves one pipeline setting on the server (`POST /settings`). */
export function saveServerSetting(settings: Settings, change: Record<string, unknown>): Promise<unknown> {
  return api(settings, withSpeaker(settings, '/settings'), { method: 'POST', body: JSON.stringify(change) });
}

/** A stored recording's WAV bytes, for playback in Review. */
export function clipAudio(settings: Settings, clipId: string): Promise<ArrayBuffer> {
  return api<ArrayBuffer>(settings, withSpeaker(settings, `/clips/${encodeURIComponent(clipId)}/audio`), {}, 'bytes');
}

/** Freezes his test set after the onboarding test sentences. */
export function freezeTestSet(settings: Settings): Promise<unknown> {
  return api(settings, withSpeaker(settings, '/teach/freeze'), { method: 'POST' });
}

export type ClipUpload = { wav: Uint8Array; text: string; phraseId?: string | null; promptId?: string | null; split: 'train' | 'test'; condition: 'quiet' | 'noisy' };

const UPLOAD_TIMEOUT_MS = 30_000;

/** The audio part of the form: a Blob on web, a cache file on the phone (expo-file-system's File is a Blob). */
async function audioPart(wav: Uint8Array): Promise<Blob> {
  if (Platform.OS === 'web') return new Blob([wav.buffer as ArrayBuffer], { type: 'audio/wav' });
  const file = new File(Paths.cache, 'teach-upload.wav');
  file.create({ overwrite: true });
  await file.write(wav);
  return file as unknown as Blob;
}

/** Uploads one Teach recording as multipart (`POST /clips`); the server's own sentence is shown on failure. */
export async function uploadClip(settings: Settings, clip: ClipUpload): Promise<TeachProgress | null> {
  const { serverUrl, token } = settings.dev;
  if (!serverUrl || !token) throw new ApiError('The server is not set. Add it in the developer panel.');
  const form = new FormData();
  form.append('audio', await audioPart(clip.wav), 'clip.wav');
  form.append('text', clip.text);
  if (clip.phraseId) form.append('phrase_id', clip.phraseId);
  if (clip.promptId) form.append('prompt_id', clip.promptId);
  form.append('split', clip.split);
  form.append('condition', clip.condition);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
  // On the phone, expo/fetch is the client that sends an expo-file-system File as a form part.
  const send = (Platform.OS === 'web' ? fetch : expoFetch) as typeof fetch;
  let response: Response;
  try {
    response = await send(`${serverUrl}${withSpeaker(settings, '/clips')}`, { method: 'POST', body: form, headers: { Authorization: `Bearer ${token}` }, signal: controller.signal });
  } catch {
    throw new ApiError('The recording did not upload. Check the connection and tap Keep again.');
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 401 || response.status === 403) throw new ApiError('The app token is wrong. Check the developer panel.');
  const body = (await response.json().catch(() => null)) as { detail?: unknown; progress?: unknown } | null;
  if (!response.ok) throw new ApiError(typeof body?.detail === 'string' ? body.detail : `The recording was not saved (status ${response.status}). Tap Keep again.`);
  const progress = progressSchema.safeParse(body?.progress);
  return progress.success ? progress.data : null;
}
