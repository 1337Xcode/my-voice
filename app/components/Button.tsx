/** The app's pill button: primary (maroon), outline (white with a dark border) or quiet (text only); 52 pt tall. */
import type { LucideIcon } from 'lucide-react-native';
import { Pressable, StyleProp, StyleSheet, ViewStyle } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, pill, space, target } from '@/theme';

type Props = {
  label: string;
  onPress: () => void;
  kind?: 'primary' | 'outline' | 'quiet';
  icon?: LucideIcon;
  disabled?: boolean;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
};

export function Button({ label, onPress, kind = 'outline', icon: Icon, disabled = false, accessibilityHint, style }: Props) {
  const iconColour = kind === 'primary' ? colors.accentText : colors.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.base, styles[kind], disabled && styles.disabled, pressed && styles.pressed, style]}>
      {Icon ? <Icon size={20} color={iconColour} strokeWidth={2} /> : null}
      <AppText variant="label" tone={kind === 'primary' ? 'inverse' : 'default'} numberOfLines={1}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { minHeight: target.min + 4, paddingHorizontal: space.xl, borderRadius: pill, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.sm },
  primary: { backgroundColor: colors.accent },
  outline: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.text },
  quiet: { backgroundColor: 'transparent', paddingHorizontal: space.md },
  disabled: { opacity: 0.4 },
  pressed: { opacity: 0.75 },
});
