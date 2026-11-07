/** Setup steps 6 and 7: Make my model with live status, then Done with his model's score against stock. */
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { useSettings } from '@/features/settings/SettingsProvider';
import { percent, shortVersion } from '@/features/teach/ModelCard';
import { fetchParsed, resultsSchema, stateSchema, type Results, type ServerState } from '@/features/teach/teachApi';
import { trainingLine, useTraining } from '@/features/teach/useTraining';
import { colors, pill, space } from '@/theme';

export function TrainStep({ onNext }: { onNext: () => void }) {
  const training = useTraining();
  const { status } = training;
  const ended = status !== null && ['promoted', 'not_better', 'failed'].includes(status.state);

  return (
    <View style={styles.step}>
      <AppText variant="title" accessibilityRole="header">
        Make my model
      </AppText>
      <AppText tone="muted">It takes about five minutes. Your phrases already work while it trains.</AppText>
      {status && status.state !== 'idle' ? (
        <View style={styles.status} accessibilityLiveRegion="polite">
          <AppText variant="label">{trainingLine(status)}</AppText>
          {training.running ? (
            <View style={styles.track}>
              <View style={[styles.fill, { width: `${Math.round((status.progress ?? 0.03) * 100)}%` }]} />
            </View>
          ) : null}
        </View>
      ) : null}
      {training.error ? <ErrorNote message={training.error} onRetry={() => void training.start()} /> : null}
      {training.running || ended ? <Button kind="primary" label={ended ? 'See my model' : 'Continue while it trains'} onPress={onNext} /> : null}
      {ended ? <Button label="Train again" onPress={() => void training.start()} disabled={training.starting} /> : null}
      {training.running || ended ? null : (
        <Button kind="primary" label={training.starting ? 'Starting' : 'Make my model'} onPress={() => void training.start()} disabled={training.starting} />
      )}
    </View>
  );
}

/** "Your model v1: understands 64% of words on your test sentences (stock: 22%)", or where it stands if not trained yet. */
export function DoneStep({ onFinish }: { onFinish: () => void }) {
  const { settings } = useSettings();
  const [data, setData] = useState<{ state: ServerState; results: Results } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setError(null);
    Promise.all([fetchParsed(settings, '/state', stateSchema), fetchParsed(settings, '/results', resultsSchema)])
      .then(([state, results]) => setData({ state, results }))
      .catch((e: Error) => setError(e.message));
    // Loads once per attempt; the settings only supply the address.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const active = data?.state.registry?.active ?? null;
  const mine = data?.results.learning.find((row) => row.version === active)?.quiet ?? null;
  const stock = data?.results.headline.find((row) => row.kind === 'stock')?.quiet ?? null;

  return (
    <View style={styles.step}>
      <AppText variant="title" accessibilityRole="header">
        Done
      </AppText>
      {!data && !error ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={() => setAttempt((n) => n + 1)} /> : null}
      {data && active && mine ? (
        <AppText variant="heading" testID="done-score">
          Your model {shortVersion(active)}: understands {percent(mine.words_understood)} of words on your test sentences (stock: {percent(stock?.words_understood)}).
        </AppText>
      ) : null}
      {data && !(active && mine) ? <AppText variant="heading">Your model is not ready yet. Teach shows its progress and score.</AppText> : null}
      <Button kind="primary" label="Start talking" onPress={onFinish} />
    </View>
  );
}

const styles = StyleSheet.create({
  step: { gap: space.xl },
  status: { gap: space.sm },
  track: { height: 8, borderRadius: pill, backgroundColor: colors.tint, overflow: 'hidden' },
  fill: { height: 8, borderRadius: pill, backgroundColor: colors.accent },
});
