/** Teach › Record: the next prompt to read, recorded and kept one at a time, with today's progress (spec 11.5). */
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { colors, radius, space } from '@/theme';
import { PromptRecorder } from './PromptRecorder';
import { usePromptQueue } from './usePromptQueue';

/** "Phrase 3 of 36 · first take", "Practice sentence" or "A sentence like yours". */
function captionOf(queue: ReturnType<typeof usePromptQueue>): string {
  if (queue.position) return `Phrase ${queue.position.index} of ${queue.position.of} · ${queue.position.take === 1 ? 'first' : 'second'} take`;
  return queue.prompt?.kind === 'like_yours' ? 'A sentence like yours' : 'Practice sentence';
}

export function RecordCard() {
  const queue = usePromptQueue();
  const { prompt, progress } = queue;

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <AppText variant="heading">Record</AppText>
        {progress ? (
          <AppText variant="caption" tone="muted" testID="teach-progress">
            {progress.today} today · {progress.minutes} min in all
          </AppText>
        ) : null}
      </View>
      {queue.loading && !prompt ? <ActivityIndicator color={colors.muted} /> : null}
      {queue.error ? <ErrorNote message={queue.error} onRetry={queue.reload} /> : null}
      {prompt && prompt.kind !== 'done' ? <PromptRecorder text={prompt.text} caption={captionOf(queue)} onKeep={queue.keep} onSkip={queue.canSkip ? queue.skip : undefined} /> : null}
      {prompt?.kind === 'done' ? (
        <View style={styles.empty}>
          <AppText>Everything is recorded. New sentences appear as your phrases change.</AppText>
        </View>
      ) : null}
      {!queue.loading && !queue.error && prompt === null ? (
        <View style={styles.empty}>
          <AppText>You skipped the rest of your phrases.</AppText>
          <Button label="Show them again" onPress={queue.clearSkips} style={styles.start} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.md },
  header: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: space.md, flexWrap: 'wrap' },
  empty: { gap: space.md, padding: space.xl, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
  start: { alignSelf: 'flex-start' },
});
