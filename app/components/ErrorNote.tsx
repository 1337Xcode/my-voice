/** A plain error sentence with a Retry button. */
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, radius, space, target } from '@/theme';

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={styles.box} accessibilityRole="alert">
      <AppText tone="danger">{message}</AppText>
      {onRetry ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={({ pressed }) => [styles.retry, pressed && styles.pressed]}>
          <AppText variant="label">Retry</AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { gap: space.md, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  retry: { alignSelf: 'flex-start', minHeight: target.min, paddingHorizontal: space.xl, justifyContent: 'center', borderRadius: radius, borderWidth: 1, borderColor: colors.border },
  pressed: { opacity: 0.6 },
});
