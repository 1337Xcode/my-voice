/** Root layout: loads Geist, provides settings and the server connection, and hosts the tabs and Settings. */
import { Geist_400Regular, Geist_500Medium, Geist_600SemiBold, useFonts } from '@expo-google-fonts/geist';
import { DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { ConnectionProvider } from '@/features/connection/ConnectionProvider';
import { SettingsProvider } from '@/features/settings/SettingsProvider';
import { colors, fonts } from '@/theme';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = { anchor: '(tabs)' };

SplashScreen.preventAutoHideAsync();

const navigationTheme = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, background: colors.background, card: colors.background, text: colors.text, border: colors.border, primary: colors.accent },
};

export default function RootLayout() {
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
      <ConnectionProvider>
        <ThemeProvider value={navigationTheme}>
          <StatusBar style="dark" />
          <Stack screenOptions={{ headerTitleStyle: { fontFamily: fonts.semibold }, headerShadowVisible: false }}>
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
          </Stack>
        </ThemeProvider>
      </ConnectionProvider>
    </SettingsProvider>
  );
}
