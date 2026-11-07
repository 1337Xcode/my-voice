/** Calls: phone calls through the server (spec 11.6). Calling arrives in phase 6. */
import { StyleSheet } from 'react-native';

import { AppText } from '@/components/AppText';
import { Screen } from '@/components/Screen';
import { useConnection } from '@/features/connection/ConnectionProvider';

export default function CallsScreen() {
  const { ready } = useConnection();
  const configured = ready?.features.calls ?? false;
  return (
    <Screen style={styles.screen}>
      <AppText variant="heading">{configured ? 'Calling is set up on the server' : 'Calling is not set up on the server yet'}</AppText>
    </Screen>
  );
}

const styles = StyleSheet.create({ screen: { flexGrow: 1 } });
