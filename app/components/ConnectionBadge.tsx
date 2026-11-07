/** The small status line for the server connection and active model, e.g. "stock · ready". */
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { colors, space } from '@/theme';

const statusText = {
  unconfigured: 'Server not set: add it in the developer panel',
  connecting: 'Connecting',
  waking: 'Waking up the speech server',
  offline: 'No connection: phrases and typing still work',
  unauthorised: 'The app token is wrong: check the developer panel',
} as const;

/** Shows readiness with a dot whose meaning is also written out, never colour alone. */
export function ConnectionBadge() {
  const { status, ready } = useConnection();
  const isReady = status === 'ready' && ready;
  const label = isReady ? `${ready.model_version} · ready` : statusText[status as keyof typeof statusText];
  const busy = status === 'connecting' || status === 'waking';
  return (
    <View style={styles.row} accessibilityRole="text" accessibilityLabel={`Speech server: ${label}`} accessibilityLiveRegion="polite">
      {busy ? <ActivityIndicator size="small" color={colors.muted} /> : <View style={[styles.dot, { backgroundColor: isReady ? colors.accent : colors.danger }]} />}
      <AppText variant="caption" tone="muted" testID="connection-status">
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 24 },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
