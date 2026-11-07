/** Shown for a route that does not exist, with a way back to Talk. */
import { Link, Stack } from 'expo-router';
import { StyleSheet } from 'react-native';

import { AppText } from '@/components/AppText';
import { Screen } from '@/components/Screen';
import { space } from '@/theme';

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Not found' }} />
      <Screen style={styles.screen}>
        <AppText variant="heading">This screen does not exist.</AppText>
        <Link href="/" style={styles.link}>
          <AppText variant="label" tone="accent">
            Go to Talk
          </AppText>
        </Link>
      </Screen>
    </>
  );
}

const styles = StyleSheet.create({ screen: { gap: space.lg }, link: { paddingVertical: space.md } });
