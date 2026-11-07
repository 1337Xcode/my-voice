/** Text in Geist, scaled by his chosen text size and never smaller than the system size. */
import { StyleSheet, Text, TextProps } from 'react-native';

import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, textScales } from '@/theme';

export type TextVariant = 'caption' | 'body' | 'label' | 'heading' | 'title' | 'sentence';

const base: Record<TextVariant, { fontSize: number; fontFamily: string; lineHeight: number }> = {
  caption: { fontSize: 14, fontFamily: fonts.regular, lineHeight: 19 },
  body: { fontSize: 17, fontFamily: fonts.regular, lineHeight: 24 },
  label: { fontSize: 17, fontFamily: fonts.medium, lineHeight: 22 },
  heading: { fontSize: 22, fontFamily: fonts.semibold, lineHeight: 28 },
  title: { fontSize: 30, fontFamily: fonts.semibold, lineHeight: 36 },
  // The spoken sentence, facing the listener: 42 pt before his scale (spec 11.3 asks for 32 at least).
  sentence: { fontSize: 42, fontFamily: fonts.semibold, lineHeight: 50 },
};

export type TextTone = 'default' | 'muted' | 'faint' | 'accent' | 'inverse';

const toneColour: Record<TextTone, string> = {
  default: colors.text,
  muted: colors.muted,
  faint: colors.faint,
  accent: colors.accent,
  inverse: colors.accentText,
};

type Props = TextProps & {
  variant?: TextVariant;
  tone?: TextTone;
  /** Overrides the variant's size in points, still scaled by his text size. */
  size?: number;
  /** Keeps the variant's size whatever his text size, for chrome that must fit (tab labels, small pills). */
  unscaled?: boolean;
};

/** The one text component every screen uses. */
export function AppText({ variant = 'body', tone = 'default', size, unscaled = false, style, ...rest }: Props) {
  const { settings } = useSettings();
  const scale = unscaled ? 1 : textScales[settings.textSize];
  const spec = base[variant];
  const fontSize = (size ?? spec.fontSize) * scale;
  // High contrast lifts secondary text to the body colour (AAA, spec 11.10).
  const colour = settings.highContrast && (tone === 'muted' || tone === 'faint') ? colors.text : toneColour[tone];
  const lineHeight = Math.round(fontSize * (spec.lineHeight / spec.fontSize));
  return <Text {...rest} style={[styles.reset, { fontFamily: spec.fontFamily, fontSize, lineHeight, color: colour }, style]} />;
}

const styles = StyleSheet.create({ reset: { includeFontPadding: false } });
