/** Covers the app until it has an access code (the server's app token): the public web build ships without one. */
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, StyleSheet, TextInput, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, radius, space, target } from '@/theme';

const CHECK_TIMEOUT_MS = 60_000;

/** Asks the server whether `code` is a valid app token; resolves null when it is, or the reason when not. */
async function checkCode(serverUrl: string, code: string): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHECK_TIMEOUT_MS);
  try {
    const response = await fetch(`${serverUrl}/wake`, { method: 'POST', headers: { Authorization: `Bearer ${code}` }, signal: controller.signal });
    if (response.ok) return null;
    const detail = ((await response.json().catch(() => null)) as { detail?: unknown } | null)?.detail;
    return typeof detail === 'string' ? detail : `The server could not check the code (status ${response.status}). Try again.`;
  } catch {
    return 'Could not reach the speech server. Check the connection and try again.';
  } finally {
    clearTimeout(timer);
  }
}

function Field({ label, value, onChangeText, onSubmit, secure = false, numeric = false }: { label: string; value: string; onChangeText: (t: string) => void; onSubmit: () => void; secure?: boolean; numeric?: boolean }) {
  return (
    <View style={styles.field}>
      <AppText variant="caption" tone="muted">
        {label}
      </AppText>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        onSubmitEditing={onSubmit}
        secureTextEntry={secure}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete={secure ? 'password' : 'off'}
        keyboardType={numeric ? 'number-pad' : 'default'}
        style={styles.input}
      />
    </View>
  );
}

function JoinInstead({ onBack }: { onBack: () => void }) {
  const [code, setCode] = useState('');
  const digits = code.replace(/\D/g, '');
  const join = () => digits.length >= 4 && router.push({ pathname: '/c/[code]', params: { code: digits } });
  return (
    <>
      <AppText variant="title">Join a call</AppText>
      <Field label="Their call code" value={code} onChangeText={setCode} onSubmit={join} numeric />
      <Button label="Join" kind="primary" onPress={join} disabled={digits.length < 4} />
      <Button label="I have an access code" kind="quiet" onPress={onBack} />
    </>
  );
}

/** On the web, an unlock link (`/?access=<code>`) saves the code on this device and is wiped from the address bar. */
function useAccessLink(loaded: boolean, save: (token: string) => void) {
  useEffect(() => {
    if (!loaded || Platform.OS !== 'web' || typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    const code = url.searchParams.get('access')?.trim();
    if (!code) return;
    url.searchParams.delete('access');
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    save(code);
  }, [loaded, save]);
}

/** A stable "save this token" function for the unlock link. */
function useCallbackToken(updateDev: (change: { token: string }) => void) {
  return useCallback((token: string) => updateDev({ token }), [updateDev]);
}

export function AccessGate() {
  const { settings, loaded, updateDev } = useSettings();
  const { status } = useConnection();
  const [code, setCode] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);
  useAccessLink(loaded, useCallbackToken(updateDev));
  const needed = loaded && (!settings.dev.token || status === 'unauthorised');
  if (!needed) return null;

  const submit = async () => {
    const trimmed = code.trim();
    if (!trimmed || checking) return;
    setChecking(true);
    setError(null);
    const problem = await checkCode(settings.dev.serverUrl, trimmed);
    setChecking(false);
    if (problem) return setError(problem);
    updateDev({ token: trimmed });
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.cover}>
      <View style={styles.body}>
        {joining ? (
          <JoinInstead onBack={() => setJoining(false)} />
        ) : (
          <>
            <AppText variant="title">My Voice</AppText>
            {status === 'unauthorised' && settings.dev.token ? <ErrorNote message="That access code no longer works. Enter the current one." /> : null}
            <Field label="Enter your access code" value={code} onChangeText={setCode} onSubmit={() => void submit()} secure />
            {error ? <ErrorNote message={error} /> : null}
            <Button label={checking ? 'Checking…' : 'Continue'} kind="primary" onPress={() => void submit()} disabled={!code.trim() || checking} />
            {checking ? <ActivityIndicator color={colors.muted} /> : null}
            <Button label="Join a call instead" kind="quiet" onPress={() => setJoining(true)} />
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  cover: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, justifyContent: 'center', backgroundColor: colors.background },
  body: { gap: space.lg, paddingHorizontal: space.xl },
  field: { gap: space.xs },
  input: { minHeight: target.min + 4, paddingHorizontal: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, fontFamily: fonts.medium, fontSize: 18, color: colors.text },
});
