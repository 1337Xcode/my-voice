/** One sentence to read aloud, in very large text, with Record and Stop, Play back, Keep or Redo, and Skip (spec 11.5). */
import { Mic, Play, Square } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { LevelBars } from '@/features/talk/LevelBars';
import { buzz } from '@/features/talk/haptics';
import { colors, radius, space, target } from '@/theme';
import { useRecording } from './useRecording';

type Props = {
  /** The sentence he reads. */
  text: string;
  /** A short line above it, e.g. "Phrase 3 of 36". */
  caption?: string;
  /** Uploads the take; throws a plain-language error to show in place. */
  onKeep: (wav: Uint8Array) => Promise<void>;
  onSkip?: () => void;
};

export function PromptRecorder({ text, caption, onKeep, onSkip }: Props) {
  const recording = useRecording();
  const { state, reset } = recording;
  const [saving, setSaving] = useState(false);

  // A new prompt starts from a clean take.
  useEffect(() => reset(), [text, reset]);

  const keep = async () => {
    if (state.kind !== 'recorded') return;
    setSaving(true);
    try {
      await onKeep(state.wav);
      buzz('result');
      reset();
    } catch (e) {
      buzz('error');
      recording.setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.card}>
      {caption ? (
        <AppText variant="caption" tone="muted">
          {caption}
        </AppText>
      ) : null}
      <AppText variant="sentence" size={34} accessibilityRole="header" testID="teach-prompt">
        {text}
      </AppText>
      {state.kind === 'recording' ? (
        <View style={styles.live} accessibilityLiveRegion="polite" accessibilityLabel="Recording">
          <LevelBars levels={recording.levels} />
          <AppText variant="caption" tone="muted" style={styles.time}>
            Recording · {state.seconds.toFixed(0)} s
          </AppText>
        </View>
      ) : null}
      {recording.error ? <ErrorNote message={recording.error} /> : null}
      <View style={styles.actions}>
        {state.kind === 'ready' ? <Button kind="primary" label="Record" icon={Mic} onPress={() => void recording.start()} style={styles.big} /> : null}
        {state.kind === 'recording' ? <Button kind="primary" label="Stop" icon={Square} onPress={() => void recording.stop()} style={styles.big} /> : null}
        {state.kind === 'recorded' ? (
          <>
            <Button kind="primary" label={saving ? 'Saving' : 'Keep'} onPress={() => void keep()} disabled={saving} style={styles.big} />
            <View style={styles.row}>
              <Button label="Play back" icon={Play} onPress={() => void recording.play()} disabled={saving} style={styles.grow} />
              <Button label="Redo" onPress={reset} disabled={saving} style={styles.grow} />
            </View>
          </>
        ) : null}
        {onSkip && state.kind === 'ready' ? <Button kind="quiet" label="Skip this one" onPress={onSkip} style={styles.skip} /> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.lg, padding: space.xl, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
  live: { gap: space.sm },
  time: { textAlign: 'center' },
  actions: { gap: space.md },
  big: { minHeight: target.round },
  // Sized to their words, then sharing the rest; at large text sizes they wrap onto two lines.
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.md },
  grow: { flexGrow: 1 },
  skip: { alignSelf: 'center' },
});
