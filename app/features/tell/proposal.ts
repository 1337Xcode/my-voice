/** "Tell the app" (spec 14.4): turns the server's proposed setting changes into plain words and into new settings. */
import type { SettingChange } from '@/features/connection/protocol';
import type { Settings } from '@/features/settings/SettingsProvider';
import type { TextSize } from '@/theme';

const SIZES: TextSize[] = ['large', 'xl', 'huge'];
const SIZE_NAMES: Record<TextSize, string> = { large: 'Large', xl: 'Extra large', huge: 'Huge' };
// Speech rate moves in steps of 0.1 within 0.7 to 1.2.
const RATE_STEP = 0.1;
const RATE_MIN = 0.7;
const RATE_MAX = 1.2;

/** One change, ready to show and to apply. */
export type PlannedChange = { key: string; label: string; from: string; to: string; apply: Partial<Settings> };

const onOff = (value: boolean) => (value ? 'On' : 'Off');
const beforeName = (value: string) => (value === 'check' ? 'Let me check first' : 'Speak straight away');
const rateName = (rate: number) => `${Math.round(rate * 100)}%`;

/** The next text size up or down, staying within the three sizes. */
function steppedSize(current: TextSize, direction: unknown): TextSize {
  const index = SIZES.indexOf(current) + (direction === 'smaller' ? -1 : 1);
  return SIZES[Math.max(0, Math.min(SIZES.length - 1, index))];
}

function steppedRate(current: number, direction: unknown): number {
  const next = current + (direction === 'slower' ? -RATE_STEP : RATE_STEP);
  return Math.round(Math.max(RATE_MIN, Math.min(RATE_MAX, next)) * 10) / 10;
}

/** Plans one proposed change against his current settings; null for a key the app does not know. */
export function planChange(change: SettingChange, settings: Settings, voiceName: (id: string) => string): PlannedChange | null {
  const base = { key: change.key, label: change.label };
  switch (change.key) {
    case 'text_size': {
      const to = steppedSize(settings.textSize, change.to);
      return { ...base, from: SIZE_NAMES[settings.textSize], to: SIZE_NAMES[to], apply: { textSize: to } };
    }
    case 'high_contrast':
      return { ...base, from: onOff(settings.highContrast), to: onOff(change.to === true), apply: { highContrast: change.to === true } };
    case 'reduce_motion':
      return { ...base, from: onOff(settings.reduceMotion), to: onOff(change.to === true), apply: { reduceMotion: change.to === true } };
    case 'speech_rate': {
      const to = steppedRate(settings.speechRate, change.to);
      return { ...base, from: rateName(settings.speechRate), to: rateName(to), apply: { speechRate: to } };
    }
    case 'before_speaking': {
      const to = change.to === 'check' ? 'check' : 'speak';
      return { ...base, from: beforeName(settings.beforeSpeaking), to: beforeName(to), apply: { beforeSpeaking: to } };
    }
    case 'voice_id':
      return typeof change.to === 'string' ? { ...base, from: settings.voiceId ? voiceName(settings.voiceId) : 'Current voice', to: voiceName(change.to), apply: { voiceId: change.to } } : null;
    default:
      return null;
  }
}

/** The server-side fields among the applied changes, for `POST /settings`. */
export function serverFieldsOf(apply: Partial<Settings>): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  if (apply.speechRate !== undefined) fields.speech_rate = apply.speechRate;
  if (apply.beforeSpeaking !== undefined) fields.before_speaking = apply.beforeSpeaking;
  if (apply.voiceId !== undefined) fields.voice_id = apply.voiceId;
  return fields;
}
