/** Root layout: loads Geist, provides settings and the server connection, and hosts the tabs and Settings. */
import { Geist_400Regular, Geist_500Medium, Geist_600SemiBold, useFonts } from '@expo-google-fonts/geist';
import { DefaultTheme, Stack, ThemeProvider, usePathname } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { AccessGate } from '@/features/access/AccessGate';
import { IncomingCallWatcher } from '@/features/calls/IncomingCallWatcher';
import { ExperimentsSync } from '@/features/experiments/ExperimentsSync';
import { ConnectionProvider } from '@/features/connection/ConnectionProvider';
import { FirstRunRedirect } from '@/features/onboarding/FirstRunRedirect';
import { ToolkitSync } from '@/features/toolkit/ToolkitSync';
import { PhrasesProvider } from '@/features/phrases/PhrasesProvider';
import { SettingsProvider } from '@/features/settings/SettingsProvider';
import { colors, fonts, maxContentWidth } from '@/theme';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = { anchor: '(tabs)' };

SplashScreen.preventAutoHideAsync();

const navigationTheme = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, background: colors.background, card: colors.background, text: colors.text, border: colors.border, primary: colors.accent },
};

export default function RootLayout() {
  // The guest call page (/c/<code>) is for family without the app's token: no server session there.
  const isGuest = usePathname().startsWith('/c/');
  const [loaded, error] = useFonts({ Geist_400Regular, Geist_500Medium, Geist_600SemiBold });

  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync();
  }, [loaded]);

  if (!loaded) return null;

  return (
    <SettingsProvider>
      <ConnectionProvider enabled={!isGuest}>
        <PhrasesProvider enabled={!isGuest}>
          {isGuest ? null : <IncomingCallWatcher />}
          {isGuest ? null : <FirstRunRedirect />}
          {isGuest ? null : <ToolkitSync />}
          {isGuest ? null : <ExperimentsSync />}
          <ThemeProvider value={navigationTheme}>
            <StatusBar style="dark" />
            {/* On a laptop the app sits in a phone-width column in the middle of the window. */}
            <View style={styles.page}>
              <View style={styles.column}>
                <Stack screenOptions={{ headerTitleStyle: { fontFamily: fonts.semibold }, headerShadowVisible: false, headerStyle: { backgroundColor: colors.background }, contentStyle: { backgroundColor: colors.background } }}>
                  <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                  <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
                  <Stack.Screen name="call" options={{ headerShown: false, presentation: 'fullScreenModal', gestureEnabled: false }} />
                  <Stack.Screen name="incoming" options={{ headerShown: false, presentation: 'fullScreenModal', gestureEnabled: false }} />
                  <Stack.Screen name="c/[code]" options={{ headerShown: false, title: 'My Voice call' }} />
                </Stack>
                {isGuest ? null : <AccessGate />}
              </View>
            </View>
          </ThemeProvider>
        </PhrasesProvider>
      </ConnectionProvider>
    </SettingsProvider>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, alignItems: 'center', backgroundColor: colors.background },
  column: { flex: 1, width: '100%', maxWidth: maxContentWidth },
});
