/** A plain error sentence with an icon (red is the accent, so errors never rely on colour) and an optional retry. */
import { CircleAlert } from 'lucide-react-native';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { colors, radius, space } from '@/theme';

type Props = { message: string; onRetry?: () => void; retryLabel?: string };

export function ErrorNote({ message, onRetry, retryLabel = 'Try again' }: Props) {
  return (
    <View style={styles.box} accessibilityRole="alert">
      <View style={styles.row}>
        <CircleAlert size={22} color={colors.accent} strokeWidth={2} />
        <AppText style={styles.text}>{message}</AppText>
      </View>
      {onRetry ? <Button label={retryLabel} onPress={onRetry} style={styles.retry} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { gap: space.md, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  row: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  text: { flex: 1 },
  retry: { alignSelf: 'flex-start' },
});
