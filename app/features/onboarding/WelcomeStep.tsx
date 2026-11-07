/** Setup step 1: what is recorded and where it goes, in plain words, and the separate yes or no for learning from conversations. */
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Choice } from '@/components/Choice';
import { ErrorNote } from '@/components/ErrorNote';
import { useSettings } from '@/features/settings/SettingsProvider';
import { saveServerSetting } from '@/features/teach/teachApi';
import { space } from '@/theme';

const promises = [
  'My Voice records you reading sentences, so it can learn how you speak.',
  'Your recordings stay on your phone and on our speech server.',
  'Other services only ever see text, never your voice.',
  'You can delete everything at any time in Settings.',
];

export function WelcomeStep({ onAgree }: { onAgree: () => void }) {
  const { settings } = useSettings();
  const [learn, setLearn] = useState<'yes' | 'no'>('no');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const agree = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveServerSetting(settings, { learn_from_conversations: learn === 'yes' });
      onAgree();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.step}>
      <AppText variant="title" accessibilityRole="header">
        Welcome
      </AppText>
      <View style={styles.list}>
        {promises.map((line) => (
          <View key={line} style={styles.item}>
            <AppText style={styles.bullet}>•</AppText>
            <AppText style={styles.flex}>{line}</AppText>
          </View>
        ))}
      </View>
      <Choice
        label="Learn from my conversations?"
        options={[
          { value: 'yes', label: 'Yes' },
          { value: 'no', label: 'No' },
        ]}
        value={learn}
        onChange={setLearn}
      />
      <AppText variant="caption" tone="muted">
        Yes keeps the sound of what you say in Talk, so it learns faster. You can change this in Settings.
      </AppText>
      {error ? <ErrorNote message={error} onRetry={() => void agree()} /> : null}
      <Button kind="primary" label={saving ? 'Saving' : 'I agree, continue'} onPress={() => void agree()} disabled={saving} />
    </View>
  );
}

const styles = StyleSheet.create({
  step: { gap: space.xl },
  list: { gap: space.md },
  item: { flexDirection: 'row', gap: space.sm },
  bullet: { width: 14 },
  flex: { flex: 1 },
});
