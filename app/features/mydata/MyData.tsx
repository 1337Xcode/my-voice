/** Settings › My data (spec 11.7 #5, 16): Learn from my conversations, Export everything, Delete everything (type DELETE). */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { File, Paths } from 'expo-file-system';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, Switch, TextInput, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { api } from '@/features/connection/api';
import { usePhrases } from '@/features/phrases/PhrasesProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { fetchParsed, saveServerSetting, stateSchema } from '@/features/teach/teachApi';
import { colors, fonts, radius, space, target } from '@/theme';

const CONFIRM_WORD = 'DELETE';

/** Saves the zip: a browser download on web, a file in the app's documents on the phone; returns where it went. */
async function saveZip(bytes: ArrayBuffer, name: string): Promise<string> {
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    // Some browsers only download from a link that is in the page.
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    return `Downloaded ${name}.`;
  }
  const file = new File(Paths.document, name);
  file.create({ overwrite: true });
  await file.write(new Uint8Array(bytes));
  return `Saved ${name} in the app's files.`;
}

function LearnToggle() {
  const { settings, loaded } = useSettings();
  const [learn, setLearn] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loaded) return;
    fetchParsed(settings, '/state', stateSchema)
      .then((state) => setLearn(Boolean(state.settings?.learn_from_conversations)))
      .catch((e: Error) => setError(e.message));
    // The settings only supply the address and speaker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, settings.dev.speaker]);

  const change = async (next: boolean) => {
    const before = learn;
    setLearn(next);
    setError(null);
    try {
      await saveServerSetting(settings, { learn_from_conversations: next });
    } catch (e) {
      setLearn(before);
      setError(`Not changed: ${(e as Error).message}`);
    }
  };

  return (
    <View style={styles.group}>
      <Pressable style={styles.switchRow} onPress={() => learn !== null && void change(!learn)} accessibilityRole="switch" accessibilityState={{ checked: Boolean(learn), disabled: learn === null }} accessibilityLabel="Learn from my conversations">
        <View style={styles.flex}>
          <AppText variant="label">Learn from my conversations</AppText>
          <AppText variant="caption" tone="muted">
            {learn ? 'On: keeps the sound of what you say in Talk' : 'Off: Talk keeps no sound'}
          </AppText>
        </View>
        {learn === null && !error ? <ActivityIndicator color={colors.muted} /> : <Switch value={Boolean(learn)} onValueChange={(v) => void change(v)} disabled={learn === null} trackColor={{ true: colors.accent }} />}
      </Pressable>
      {error ? <ErrorNote message={error} /> : null}
    </View>
  );
}

export function MyData() {
  const { settings } = useSettings();
  const phrases = usePhrases();
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const exportAll = async () => {
    setExporting(true);
    setExportError(null);
    setExported(null);
    try {
      const bytes = await api<ArrayBuffer>(settings, `/export?speaker=${settings.dev.speaker}`, {}, 'bytes');
      setExported(await saveZip(bytes, `my-voice-${settings.dev.speaker}.zip`));
    } catch (e) {
      setExportError((e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  /** Deletes everything on the server (models included), then everything this app keeps on the phone. */
  const deleteAll = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await api(settings, `/data?speaker=${settings.dev.speaker}`, { method: 'DELETE', body: JSON.stringify({ confirm: CONFIRM_WORD }) });
      await AsyncStorage.clear();
      phrases.reload();
      setDeleted(true);
      setConfirming(false);
      setTyped('');
    } catch (e) {
      setDeleteError((e as Error).message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <View style={styles.group}>
      <AppText variant="label" accessibilityRole="header">
        My data
      </AppText>
      <View style={styles.card}>
        <LearnToggle />
        <View style={styles.divider} />
        <Button label={exporting ? 'Preparing the zip' : 'Export everything'} onPress={() => void exportAll()} disabled={exporting} style={styles.left} />
        {exported ? <AppText tone="muted">{exported}</AppText> : null}
        {exportError ? <ErrorNote message={exportError} onRetry={() => void exportAll()} /> : null}
        <View style={styles.divider} />
        {deleted ? <AppText variant="label">Everything is deleted, on the server and on this phone.</AppText> : null}
        {!confirming ? <Button label="Delete everything" onPress={() => setConfirming(true)} style={styles.left} /> : null}
        {confirming ? (
          <View style={styles.group}>
            <AppText>This deletes every recording, phrase and model, here and on the server. It cannot be undone. Type {CONFIRM_WORD} to confirm.</AppText>
            <TextInput accessibilityLabel={`Type ${CONFIRM_WORD} to confirm`} value={typed} onChangeText={setTyped} autoCapitalize="characters" autoCorrect={false} style={styles.input} />
            <View style={styles.row}>
              <Button kind="primary" label={deleting ? 'Deleting' : 'Delete everything'} onPress={() => void deleteAll()} disabled={typed.trim() !== CONFIRM_WORD || deleting} />
              <Button kind="quiet" label="Cancel" onPress={() => setConfirming(false)} disabled={deleting} />
            </View>
            {deleteError ? <ErrorNote message={deleteError} /> : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.md },
  card: { gap: space.lg, padding: space.lg, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
  switchRow: { minHeight: target.min, flexDirection: 'row', alignItems: 'center', gap: space.md },
  flex: { flex: 1 },
  divider: { height: 1, backgroundColor: colors.border },
  left: { alignSelf: 'flex-start' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  input: { minHeight: target.min, paddingHorizontal: space.md, borderRadius: space.md, borderWidth: 1, borderColor: colors.text, fontFamily: fonts.medium, fontSize: 17, color: colors.text, backgroundColor: colors.background },
});
