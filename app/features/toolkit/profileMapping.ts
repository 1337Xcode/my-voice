/**
 * Maps the AI for Accessibility toolkit's profile to this app's settings and back (API-NOTES §5).
 * Pure functions with no imports, so `node --test` can run their tests without the app's bundler.
 */

/** The app's text sizes (theme `textScales`): 1.0, 1.2 and 1.45 times. */
export type AppTextSize = 'large' | 'xl' | 'huge';

/** What the toolkit asks of this app; a key is absent when the profile says nothing about it. */
export type ToolkitPrefs = {
  textSize?: AppTextSize;
  highContrast?: boolean;
  reduceMotion?: boolean;
  /** Voice speed as a multiplier, already limited to what the voice supports (0.7 to 1.2). */
  speechRate?: number;
  largeTargets?: boolean;
  captions?: boolean;
  /** From the app's own scope `context:speech-translator`. */
  beforeSpeaking?: 'speak' | 'check';
  voiceId?: string;
};

export const APP_SCOPE = 'context:speech-translator';
export const APP_ORIGIN = 'speech-translator';

// The voice (ElevenLabs via the server) accepts speeds from 0.7 to 1.2.
const MIN_SPEECH_RATE = 0.7;
const MAX_SPEECH_RATE = 1.2;

const SCALE_PERCENT: Record<AppTextSize, number> = { large: 100, xl: 120, huge: 145 };

/** A font scale in percent to the nearest app size: under 110% is large, under 133% extra large, else huge. */
export function textSizeFromPercent(percent: number): AppTextSize {
  if (percent < 110) return 'large';
  if (percent < 133) return 'xl';
  return 'huge';
}

/** The app size as the toolkit's `fontScale` percent. */
export function percentFromTextSize(size: AppTextSize): number {
  return SCALE_PERCENT[size];
}

/** Limits a speech rate multiplier to what the voice supports, rounded to 0.05. */
export function clampSpeechRate(rate: number): number {
  return Math.round(Math.min(MAX_SPEECH_RATE, Math.max(MIN_SPEECH_RATE, rate)) * 20) / 20;
}

type Need = { dimension?: unknown; value?: unknown };

/** The profile's needs (`profile.fields.needs`) as a dimension-to-value map. */
function needsOf(profile: unknown): Record<string, unknown> {
  const needs = (profile as { fields?: { needs?: Need[] } } | null)?.fields?.needs;
  const out: Record<string, unknown> = {};
  if (Array.isArray(needs)) for (const need of needs) if (typeof need?.dimension === 'string') out[need.dimension] = need.value;
  return out;
}

const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isBool = (v: unknown): v is boolean => typeof v === 'boolean';
/** A contrast value is on when true or a named variant other than "none". */
const contrastOn = (v: unknown): boolean | undefined => (isBool(v) ? v : typeof v === 'string' ? v !== 'none' : undefined);

/**
 * Reads `getProfile` (needs) and `effectivePreferences` (settings, user-explicit last) into app preferences.
 * A setting from the effective preferences wins over the need it derives from.
 */
export function prefsFromToolkit(profile: unknown, effective: unknown): ToolkitPrefs {
  const needs = needsOf(profile);
  const settings = ((effective as { settings?: Record<string, unknown> } | null)?.settings ?? {}) as Record<string, unknown>;
  const fields = ((profile as { fields?: Record<string, unknown> } | null)?.fields ?? {}) as Record<string, unknown>;
  const prefs: ToolkitPrefs = {};

  const fontScale = isNumber(settings.fontScale) ? settings.fontScale : isNumber(needs.textSize) ? needs.textSize * 100 : undefined;
  if (fontScale !== undefined) prefs.textSize = textSizeFromPercent(fontScale);

  const contrast = contrastOn(settings.contrastMode) ?? contrastOn(needs.contrast);
  if (contrast !== undefined) prefs.highContrast = contrast;

  const motion = isBool(settings.motionReducer) ? settings.motionReducer : isBool(needs.reduceMotion) ? needs.reduceMotion : undefined;
  if (motion !== undefined) prefs.reduceMotion = motion;

  const rate = isNumber(settings.speechRate) ? settings.speechRate : isNumber(needs.readAloudRate) ? needs.readAloudRate : undefined;
  if (rate !== undefined) prefs.speechRate = clampSpeechRate(rate);

  const targets = isBool(settings.bigTargets) ? settings.bigTargets : isBool(fields.largeTargets) ? fields.largeTargets : undefined;
  if (targets !== undefined) prefs.largeTargets = targets;

  const captions = isBool(settings.showCaptions) ? settings.showCaptions : isBool(needs.captions) ? needs.captions : undefined;
  if (captions !== undefined) prefs.captions = captions;

  if (isBool(settings.askBeforeSpeaking)) prefs.beforeSpeaking = settings.askBeforeSpeaking ? 'check' : 'speak';
  if (typeof settings.voiceId === 'string' && settings.voiceId) prefs.voiceId = settings.voiceId;
  return prefs;
}

/** The app's own choices that the toolkit keeps. */
export type AppChoices = {
  textSize: AppTextSize;
  highContrast: boolean;
  reduceMotion: boolean;
  speechRate: number;
  beforeSpeaking: 'speak' | 'check';
  voiceId: string | null;
};

/** Applies the profile's preferences over his current choices; anything the profile is silent on stays as it is. */
export function choicesFromPrefs(prefs: ToolkitPrefs, mine: AppChoices): AppChoices {
  return {
    textSize: prefs.textSize ?? mine.textSize,
    highContrast: prefs.highContrast ?? mine.highContrast,
    reduceMotion: prefs.reduceMotion ?? mine.reduceMotion,
    speechRate: prefs.speechRate ?? mine.speechRate,
    beforeSpeaking: prefs.beforeSpeaking ?? mine.beforeSpeaking,
    voiceId: prefs.voiceId ?? mine.voiceId,
  };
}

/** Shared keys to write with `recordExplicitSetting` for each choice he changed (what he asks for, never a condition). */
export function sharedWrites(before: AppChoices | null, after: AppChoices): [string, unknown][] {
  const writes: [string, unknown][] = [];
  if (before?.textSize !== after.textSize) writes.push(['fontScale', percentFromTextSize(after.textSize)]);
  if (before?.highContrast !== after.highContrast) writes.push(['contrastMode', after.highContrast ? 'light' : 'none']);
  if (before?.reduceMotion !== after.reduceMotion) writes.push(['motionReducer', after.reduceMotion]);
  if (before?.speechRate !== after.speechRate) writes.push(['speechRate', after.speechRate]);
  return writes;
}

/** App-scoped settings to write with `recordScopedSettings(APP_SCOPE, ...)` when a choice changed; null when none did. */
export function scopedWrites(before: AppChoices | null, after: AppChoices): Record<string, unknown> | null {
  const out: Record<string, unknown> = {};
  if (before?.beforeSpeaking !== after.beforeSpeaking) out.askBeforeSpeaking = after.beforeSpeaking === 'check';
  if (after.voiceId && before?.voiceId !== after.voiceId) out.voiceId = after.voiceId;
  return Object.keys(out).length ? out : null;
}
