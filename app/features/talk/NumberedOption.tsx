/** One numbered option card ("1", "2", "3" in a tinted circle); tapping it speaks it. */
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, radius, space } from '@/theme';

type Props = { index: number; text: string; onPress: () => void; hint?: string };

export function NumberedOption({ index, text, onPress, hint = 'Speaks this sentence' }: Props) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Option ${index}: ${text}`}
      accessibilityHint={hint}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <View style={styles.number}>
        <AppText variant="label">{index}</AppText>
      </View>
      <AppText variant="heading" style={styles.text}>
        {text}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', gap: space.lg, minHeight: 76, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pressed: { backgroundColor: colors.tint },
  number: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tint },
  text: { flex: 1 },
});
