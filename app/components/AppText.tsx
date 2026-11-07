/** Text in Geist, scaled by his chosen text size and never smaller than the system size. */
import { StyleSheet, Text, TextProps } from 'react-native';

import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, textScales } from '@/theme';

type Variant = 'body' | 'caption' | 'label' | 'title' | 'heading' | 'sentence';

const base: Record<Variant, { fontSize: number; fontFamily: string; lineHeight: number }> = {
  caption: { fontSize: 13, fontFamily: fonts.regular, lineHeight: 18 },
  body: { fontSize: 17, fontFamily: fonts.regular, lineHeight: 24 },
  label: { fontSize: 17, fontFamily: fonts.medium, lineHeight: 22 },
  heading: { fontSize: 20, fontFamily: fonts.semibold, lineHeight: 26 },
  title: { fontSize: 28, fontFamily: fonts.semibold, lineHeight: 34 },
  // The spoken sentence: 32 pt minimum before his scale (spec 11.3).
  sentence: { fontSize: 34, fontFamily: fonts.semibold, lineHeight: 42 },
};

type Props = TextProps & { variant?: Variant; tone?: 'default' | 'muted' | 'faint' | 'accent' | 'danger' | 'inverse' };

const toneColour = {
  default: colors.text,
  muted: colors.muted,
  faint: colors.faint,
  accent: colors.accent,
  danger: colors.danger,
  inverse: colors.accentText,
};

/** The one text component every screen uses. */
export function AppText({ variant = 'body', tone = 'default', style, ...rest }: Props) {
  const { settings } = useSettings();
  const scale = textScales[settings.textSize];
  const spec = base[variant];
  return (
    <Text
      {...rest}
      style={[
        styles.reset,
        { fontFamily: spec.fontFamily, fontSize: spec.fontSize * scale, lineHeight: spec.lineHeight * scale, color: toneColour[tone] },
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({ reset: { includeFontPadding: false } });
