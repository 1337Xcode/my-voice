/** Teach › Your model: the active version, words understood against stock, the trend, and Improve now with live status (spec 11.5). */
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { colors, pill, radius, space } from '@/theme';
import { LearningChart } from './LearningChart';
import type { Results, ServerState } from './teachApi';
import { trainingLine, useTraining } from './useTraining';

/** "p1-whisper-lora-v2" becomes "v2", as the Results table names it. */
export function shortVersion(name: string): string {
  return name.split('-').pop() ?? name;
}

/** A whole-number percentage, or a dash when not scored. */
export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : `${Math.round(value)}%`;
}

type Props = { state: ServerState; results: Results | null; onModelUpdate: () => void };

/** One condition's number for his model, with stock underneath for comparison. */
function Score({ label, mine, stock }: { label: string; mine: number | null | undefined; stock: number | null | undefined }) {
  return (
    <View style={styles.score} accessible accessibilityLabel={`${label}: ${percent(mine)} of words understood, stock ${percent(stock)}`}>
      <AppText variant="caption" tone="muted">
        {label}
      </AppText>
      <AppText variant="title">{percent(mine)}</AppText>
      <AppText variant="caption" tone="muted">
        Stock {percent(stock)}
      </AppText>
    </View>
  );
}

export function ModelCard({ state, results, onModelUpdate }: Props) {
  const training = useTraining(onModelUpdate);
  const active = state.registry?.active ?? null;
  const trained = state.model_version !== 'stock' && active !== null;
  const mine = results?.learning.find((row) => row.version === active) ?? null;
  const stock = results?.headline.find((row) => row.kind === 'stock') ?? null;
  const trainedOn = active ? state.registry?.versions?.[active]?.train_clips : undefined;
  const points = (results?.learning ?? []).map((row) => ({ label: shortVersion(row.version), quiet: row.quiet?.words_understood ?? null, babble: row.babble_5db?.words_understood ?? null }));
  const status = training.status;
  const showStatus = status && status.state !== 'idle';

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <AppText variant="caption" tone="muted">
          Your model
        </AppText>
        <AppText variant="heading" testID="model-version">
          {trained ? shortVersion(active) : 'Not trained yet'}
        </AppText>
        {trainedOn ? (
          <AppText variant="caption" tone="muted">
            Trained on {trainedOn} clips{state.clips.test ? ` · ${state.clips.test} kept for testing` : ''}
          </AppText>
        ) : null}
      </View>

      {trained || stock ? (
        <View style={styles.scores}>
          <Score label="Quiet" mine={trained ? mine?.quiet?.words_understood : null} stock={stock?.quiet?.words_understood} />
          <Score label="Babble" mine={trained ? mine?.babble_5db?.words_understood : null} stock={stock?.babble_5db?.words_understood} />
        </View>
      ) : (
        <AppText tone="muted">Record your test sentences, then make your model.</AppText>
      )}
      {points.length > 1 ? <LearningChart points={points} compact /> : null}

      {showStatus ? (
        <View style={styles.status} accessibilityLiveRegion="polite">
          <AppText variant="label" testID="training-status">
            {trainingLine(status)}
          </AppText>
          {training.running && typeof status.progress === 'number' ? (
            <View style={styles.track} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(status.progress * 100) }}>
              <View style={[styles.fill, { width: `${Math.round(status.progress * 100)}%` }]} />
            </View>
          ) : null}
        </View>
      ) : null}
      {training.error ? <ErrorNote message={training.error} onRetry={() => void training.start()} /> : null}
      <Button
        label={training.running ? 'Improving' : training.starting ? 'Starting' : 'Improve now'}
        onPress={() => void training.start()}
        disabled={training.running || training.starting}
        accessibilityHint="Trains a new version of your model on everything you have recorded"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.lg, padding: space.xl, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
  head: { gap: 2 },
  scores: { flexDirection: 'row', gap: space.xl },
  score: { flex: 1, gap: 2 },
  status: { gap: space.sm },
  track: { height: 8, borderRadius: pill, backgroundColor: colors.tint, overflow: 'hidden' },
  fill: { height: 8, borderRadius: pill, backgroundColor: colors.accent },
});
