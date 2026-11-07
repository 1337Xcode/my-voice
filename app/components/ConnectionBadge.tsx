/** The small status line for the server connection and active model, e.g. "stock · ready". */
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { colors, space } from '@/theme';

const statusText = {
  unconfigured: 'Server not set',
  connecting: 'Connecting',
  waking: 'Waking up the speech server',
  offline: 'Offline',
  unauthorised: 'App token is wrong',
} as const;

/** Readiness as words beside a dot (filled when ready, hollow otherwise), never colour alone. */
export function ConnectionBadge() {
  const { status, ready } = useConnection();
  const isReady = status === 'ready' && ready;
  const label = isReady ? `${ready.model_version} · ready` : statusText[status as keyof typeof statusText];
  const busy = status === 'connecting' || status === 'waking';
  return (
    <View style={styles.row} accessibilityRole="text" accessibilityLabel={`Speech server: ${label}`} accessibilityLiveRegion="polite">
      {busy ? <ActivityIndicator size="small" color={colors.muted} /> : <View style={[styles.dot, isReady ? styles.filled : styles.hollow]} />}
      <AppText variant="caption" tone="muted" testID="connection-status" numberOfLines={1} unscaled style={styles.label}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexShrink: 1, flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 24 },
  label: { flexShrink: 1 },
  dot: { width: 9, height: 9, borderRadius: 5 },
  filled: { backgroundColor: colors.text },
  hollow: { borderWidth: 1.5, borderColor: colors.muted },
});
