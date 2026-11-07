/** Setup step 4: the ten test sentences (ta01 to ta10), recorded once each, then the test set is frozen. */
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { useSettings } from '@/features/settings/SettingsProvider';
import { PromptRecorder } from '@/features/teach/PromptRecorder';
import { fetchParsed, freezeTestSet, testSentencesSchema, uploadClip, type TestSentence } from '@/features/teach/teachApi';
import { colors, space } from '@/theme';

export function TestSentencesStep({ onNext }: { onNext: () => void }) {
  const { settings } = useSettings();
  const [sentences, setSentences] = useState<TestSentence[] | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [freezing, setFreezing] = useState(false);

  const load = useCallback(() => {
    setError(null);
    fetchParsed(settings, '/teach/test-sentences', testSentencesSchema)
      .then((body) => setSentences(body.sentences))
      .catch((e: Error) => setError(e.message));
  }, [settings]);

  // Loads once; a reload happens after each kept take.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  const current = sentences?.find((s) => !s.recorded && !skipped.includes(s.id)) ?? null;
  const recorded = sentences?.filter((s) => s.recorded).length ?? 0;

  const keep = async (wav: Uint8Array) => {
    if (!current) return;
    await uploadClip(settings, { wav, text: current.text, promptId: current.id, split: 'test', condition: 'quiet' });
    setSentences((list) => list?.map((s) => (s.id === current.id ? { ...s, recorded: true } : s)) ?? null);
  };

  /** Freezes the test set (the server also builds the babble versions), then moves on. */
  const finish = async () => {
    setFreezing(true);
    setError(null);
    try {
      await freezeTestSet(settings);
      onNext();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setFreezing(false);
    }
  };

  return (
    <View style={styles.step}>
      <AppText variant="title" accessibilityRole="header">
        Test sentences
      </AppText>
      <AppText tone="muted">Read each one once. They measure how well it understands you, and are never trained on.</AppText>
      {!sentences && !error ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={sentences ? () => void finish() : load} /> : null}
      {current && sentences ? (
        <PromptRecorder
          text={current.text}
          caption={`Test sentence ${sentences.indexOf(current) + 1} of ${sentences.length}`}
          onKeep={keep}
          onSkip={() => setSkipped((list) => [...list, current.id])}
        />
      ) : null}
      {sentences && !current ? (
        <>
          <AppText variant="label">
            {recorded} of {sentences.length} recorded.
          </AppText>
          {recorded > 0 ? (
            <Button kind="primary" label={freezing ? 'Saving' : 'Save my test set'} onPress={() => void finish()} disabled={freezing} />
          ) : null}
          {skipped.length ? <Button label="Record the skipped ones" onPress={() => setSkipped([])} /> : null}
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({ step: { gap: space.xl } });
