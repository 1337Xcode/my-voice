/** Talk: the main screen. Phase 0 shows the connection to the speech server. */
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ConnectionBadge } from '@/components/ConnectionBadge';
import { Screen } from '@/components/Screen';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { colors, space } from '@/theme';

export default function TalkScreen() {
  const { status, lastError } = useConnection();
  return (
    <Screen scroll={false} style={styles.screen}>
      <ConnectionBadge />
      <View style={styles.centre}>
        {status === 'waking' ? (
          <View style={styles.waking} accessibilityLiveRegion="polite">
            <ActivityIndicator size="large" color={colors.muted} />
            <AppText variant="heading" tone="muted">
              Waking up the speech server
            </AppText>
          </View>
        ) : null}
        {lastError ? <AppText tone="danger">{lastError}</AppText> : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  centre: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg },
  waking: { alignItems: 'center', gap: space.lg },
});
