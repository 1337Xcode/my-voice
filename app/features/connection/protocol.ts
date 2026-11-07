/** Message types exchanged with the speech server over /ws (spec section 12.1), validated with zod on arrival. */
import { z } from 'zod';

// realtime_voice and lips are the experiment flags (EXP-SPEC): absent or false keeps the core product unchanged.
const features = z.object({ calls: z.boolean(), toolkit: z.boolean(), partials: z.boolean(), realtime_voice: z.boolean(), lips: z.boolean() }).partial();

const ready = z.object({
  type: z.literal('ready'),
  speaker: z.string(),
  model_version: z.string(),
  voice_id: z.string().nullable().optional(),
  features: features.optional(),
});

const candidate = z.object({ id: z.string(), text: z.string(), p: z.number().optional(), sources: z.array(z.string()).optional() });

const result = z.object({
  type: z.literal('result'),
  turn_id: z.string(),
  action: z.enum(['speak', 'pick', 'again']),
  candidates: z.array(candidate),
  chosen_id: z.string().nullable().optional(),
  timings: z.record(z.string(), z.unknown()).optional(),
});

const audio = z.object({
  type: z.literal('audio'),
  turn_id: z.string().nullable().optional(),
  phrase_id: z.string().nullable().optional(),
  format: z.string(),
  text: z.string().optional(),
  data: z.string(),
});

/** One settings change he asked for in his own words ("Tell the app", spec 14.4). */
const settingChange = z.object({ key: z.string(), from: z.unknown().optional(), to: z.unknown(), label: z.string() });

const serverMessage = z.discriminatedUnion('type', [
  ready,
  result,
  audio,
  z.object({ type: z.literal('endpoint'), turn_id: z.string() }),
  z.object({ type: z.literal('partial'), turn_id: z.string(), text: z.string() }),
  z.object({ type: z.literal('ignored'), turn_id: z.string(), reason: z.string() }),
  z.object({ type: z.literal('learned'), turn_id: z.string().optional(), kind: z.string().optional() }),
  z.object({ type: z.literal('error'), code: z.string(), message: z.string() }),
  z.object({ type: z.literal('call_status'), call_id: z.string(), state: z.enum(['dialling', 'ringing', 'connected', 'ended', 'failed']), detail: z.string().nullable().optional() }),
  z.object({ type: z.literal('partner_caption'), text: z.string(), source: z.string().optional(), partial: z.boolean().optional(), segment_id: z.string().optional() }),
  // Experiments (EXP-SPEC 9.2): streamed voice chunks, and lips setup and status.
  z.object({ type: z.literal('audio_chunk'), turn_id: z.string(), seq: z.number(), format: z.string(), sample_rate: z.number(), data: z.string(), final: z.boolean() }),
  z.object({ type: z.literal('experiments'), realtime_voice: z.boolean(), lips: z.boolean().optional(), session_id: z.string().optional() }),
  z.object({ type: z.literal('lips_setup'), step: z.string(), ok: z.boolean(), reason: z.string().nullable().optional(), offset_ms: z.number().nullable().optional(), thresholds: z.record(z.string(), z.number()).nullable().optional() }),
  z.object({ type: z.literal('lips_turn'), turn_id: z.string(), who: z.enum(['him', 'other', 'unknown']), lip_active_ratio: z.number().nullable().optional(), face_visible_pct: z.number().nullable().optional(), endpoint: z.string().nullable().optional() }),
  z.object({ type: z.literal('incoming_call'), call_id: z.string(), name: z.string().nullable().optional(), kind: z.string().optional() }),
  z.object({ type: z.literal('training'), state: z.string(), progress: z.number().nullable().optional(), eta_s: z.number().nullable().optional(), message: z.string().nullable().optional() }),
  z.object({ type: z.literal('model_update'), model_version: z.string(), metrics: z.record(z.string(), z.unknown()).nullable().optional() }),
  z.object({
    type: z.literal('settings_proposal'),
    turn_id: z.string(),
    changes: z.array(settingChange),
    heard: z.string().nullable().optional(),
  }),
]);

export type ReadyMessage = z.infer<typeof ready>;
export type Candidate = z.infer<typeof candidate>;
export type ResultMessage = z.infer<typeof result>;
export type AudioMessage = z.infer<typeof audio>;
export type ServerMessage = z.infer<typeof serverMessage>;
export type SettingChange = z.infer<typeof settingChange>;
export type CallState = Extract<ServerMessage, { type: 'call_status' }>['state'];

/** Any JSON message the app sends; each has a string `type`. */
export type ClientMessage = { type: string } & Record<string, unknown>;

/** Parses a raw JSON value into a known server message, or null for anything unknown or malformed. */
export function parseServerMessage(value: unknown): ServerMessage | null {
  const parsed = serverMessage.safeParse(value);
  return parsed.success ? parsed.data : null;
}
