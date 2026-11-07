/** Setup step 5: each phrase recorded twice; his first 15 phrases are the minimum to finish. */
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { PromptRecorder } from '@/features/teach/PromptRecorder';
import { usePromptQueue } from '@/features/teach/usePromptQueue';
import { colors, pill, space } from '@/theme';

const MINIMUM_PHRASES = 15;

export function PhraseRecordingStep({ onNext }: { onNext: () => void }) {
  const queue = usePromptQueue();
  const { prompt, position } = queue;
  const needed = Math.min(MINIMUM_PHRASES, queue.phraseCount);
  const done = Math.min(queue.phrasesDone, needed);
  const enough = queue.phraseCount > 0 && queue.phrasesDone >= needed;

  return (
    <View style={styles.step}>
      <AppText variant="title" accessibilityRole="header">
        Your phrases, twice each
      </AppText>
      {queue.phraseCount ? (
        <View style={styles.meter} accessibilityRole="progressbar" accessibilityLabel={`${done} of ${needed} phrases done`} accessibilityValue={{ min: 0, max: needed, now: done }}>
          <AppText variant="label">
            {done} of {needed} phrases done
          </AppText>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${needed ? (done / needed) * 100 : 0}%` }]} />
          </View>
        </View>
      ) : null}
      {queue.loading && !prompt ? <ActivityIndicator color={colors.muted} /> : null}
      {queue.error ? <ErrorNote message={queue.error} onRetry={queue.reload} /> : null}
      {prompt?.kind === 'phrase' && position ? (
        <PromptRecorder text={prompt.text} caption={`Phrase ${position.index} of ${position.of} · ${position.take === 1 ? 'first' : 'second'} take`} onKeep={queue.keep} onSkip={queue.skip} />
      ) : null}
      {prompt && prompt.kind !== 'phrase' ? <AppText variant="label">Every phrase is recorded.</AppText> : null}
      {!queue.loading && !queue.error && prompt === null ? <Button label="Show the skipped phrases" onPress={queue.clearSkips} /> : null}
      <Button kind={enough ? 'primary' : 'outline'} label="Continue" onPress={onNext} disabled={!enough} accessibilityHint={enough ? undefined : `Record ${needed} phrases first, or skip this step`} />
    </View>
  );
}

const styles = StyleSheet.create({
  step: { gap: space.xl },
  meter: { gap: space.sm },
  track: { height: 8, borderRadius: pill, backgroundColor: colors.tint, overflow: 'hidden' },
  fill: { height: 8, borderRadius: pill, backgroundColor: colors.accent },
});
