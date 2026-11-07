/** The confirm card for "Tell the app": each change in plain words; nothing changes until he taps Apply. */
import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { z } from 'zod';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { api } from '@/features/connection/api';
import type { SettingChange } from '@/features/connection/protocol';
import { useServerData } from '@/features/connection/useServerData';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, radius, space } from '@/theme';
import { planChange, serverFieldsOf } from './proposal';

const voicesSchema = z.object({ voices: z.array(z.object({ id: z.string(), name: z.string() })) });

type Props = { changes: SettingChange[]; heard: string | null; onDone: () => void; onTryAgain: () => void };

export function ProposalCard({ changes, heard, onDone, onTryAgain }: Props) {
  const { settings, update } = useSettings();
  const voices = useServerData<unknown>('/voices');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const parsedVoices = voicesSchema.safeParse(voices.data);
  const voiceName = (id: string) => (parsedVoices.success ? parsedVoices.data.voices.find((v) => v.id === id)?.name : undefined) ?? 'Another voice';
  const planned = changes.map((change) => planChange(change, settings, voiceName)).filter((p) => p !== null);

  if (planned.length === 0)
    return (
      <View style={styles.wrap}>
        <AppText variant="title">I didn&apos;t catch a settings request.</AppText>
        <AppText tone="muted">Try again or open Settings.</AppText>
        <View style={styles.actions}>
          <Button label="Open Settings" onPress={() => router.push('/settings')} style={styles.flex} />
          <Button label="Try again" kind="primary" onPress={onTryAgain} style={styles.flex} />
        </View>
      </View>
    );

  const apply = async () => {
    const all = Object.assign({}, ...planned.map((p) => p.apply));
    const serverFields = serverFieldsOf(all);
    setSaving(true);
    try {
      if (Object.keys(serverFields).length) await api(settings, `/settings?speaker=${settings.dev.speaker}`, { method: 'POST', body: JSON.stringify(serverFields) });
      update(all);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.wrap}>
      <AppText variant="title" accessibilityRole="header">
        Change {planned.length === 1 ? 'this setting' : 'these settings'}?
      </AppText>
      {heard ? <AppText tone="muted">You said: “{heard}”</AppText> : null}
      {planned.map((change) => (
        <View key={change.key} style={styles.change} accessible accessibilityLabel={`${change.label}: from ${change.from} to ${change.to}`}>
          <AppText variant="label">{change.label}</AppText>
          <AppText tone="muted">
            {change.from} → {change.to}
          </AppText>
        </View>
      ))}
      {error ? <ErrorNote message={error} /> : null}
      <View style={styles.actions}>
        <Button label="Cancel" onPress={onDone} style={styles.flex} />
        <Button label="Apply" kind="primary" onPress={() => void apply()} disabled={saving} style={styles.flex} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  wrap: { flex: 1, justifyContent: 'center', gap: space.md },
  change: { gap: space.xs, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  actions: { flexDirection: 'row', gap: space.md, marginTop: space.sm },
});
