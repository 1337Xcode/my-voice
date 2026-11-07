/** A round in-call button with its label underneath, like the iPhone call screen's grid. */
import type { LucideIcon } from 'lucide-react-native';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, space } from '@/theme';

const SIZE = 76;

type Props = { label: string; icon: LucideIcon; onPress: () => void; active?: boolean; busy?: boolean; disabled?: boolean; tone?: 'plain' | 'hangup' };

export function CallButton({ label, icon: Icon, onPress, active = false, busy = false, disabled = false, tone = 'plain' }: Props) {
  const fill = tone === 'hangup' ? colors.accent : active ? colors.ink : colors.tint;
  const iconColour = tone === 'hangup' || active ? colors.inkText : colors.text;
  return (
    <View style={styles.wrap}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ disabled: disabled || busy, busy }}
        disabled={disabled || busy}
        onPress={onPress}
        style={({ pressed }) => [styles.circle, { backgroundColor: fill }, pressed && styles.pressed, disabled && styles.disabled]}>
        {busy ? <ActivityIndicator color={colors.accent} /> : <Icon size={30} color={iconColour} strokeWidth={2.2} />}
      </Pressable>
      <AppText variant="caption" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', gap: space.sm, minWidth: SIZE + space.lg },
  circle: { width: SIZE, height: SIZE, borderRadius: SIZE / 2, alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.7 },
  disabled: { opacity: 0.4 },
});
