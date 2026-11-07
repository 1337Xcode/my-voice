/** A smaller round secondary control with its label underneath (Type, Cancel), beside the Talk button. */
import type { LucideIcon } from 'lucide-react-native';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, space, target } from '@/theme';

type Props = { label: string; icon: LucideIcon; onPress: () => void; disabled?: boolean };

export function RoundAction({ label, icon: Icon, onPress, disabled = false }: Props) {
  return (
    <View style={styles.wrap}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ disabled }}
        disabled={disabled}
        onPress={onPress}
        style={({ pressed }) => [styles.circle, pressed && styles.pressed, disabled && styles.disabled]}>
        <Icon size={26} color={colors.text} strokeWidth={2} />
      </Pressable>
      <AppText variant="caption" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </AppText>
    </View>
  );
}

/** Keeps the Talk button centred when one side has no control. */
export function RoundSpacer() {
  return <View style={styles.wrap} />;
}

const styles = StyleSheet.create({
  wrap: { width: target.round + space.lg, alignItems: 'center', gap: space.sm },
  circle: { width: target.round - 8, height: target.round - 8, borderRadius: target.round, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  pressed: { backgroundColor: colors.tint },
  disabled: { opacity: 0.4 },
});
