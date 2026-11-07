/** Experiments (EXP-SPEC): features still being tested, each off until he switches it on, with its measured numbers. */
import { router, Stack } from 'expo-router';
import { ScanFace } from 'lucide-react-native';
import { ActivityIndicator, Pressable, StyleSheet, Switch, View } from 'react-native';
import { z } from 'zod';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import { useServerData } from '@/features/connection/useServerData';
import { useExperimentAvailability } from '@/features/experiments/ExperimentsSync';
import { updateExperiments, useExperimentChoices } from '@/features/experiments/store';
import { colors, radius, space, target } from '@/theme';

const reportSchema = z.object({
  realtime: z.object({
    streamed_turns: z.number(),
    first_sound_ms_median: z.number().nullable(),
    target_ms: z.number(),
    needed_turns: z.number(),
    met: z.boolean(),
  }),
  lips_report: z.object({
    capture: z.object({ seconds: z.number(), fps_median: z.number().nullable(), seconds_at_24_pct: z.number(), met: z.boolean() }).nullable(),
    sync_offsets_ms: z.array(z.number()),
  }),
});
type Report = z.infer<typeof reportSchema>;

function SwitchRow({ label, value, onChange }: { label: string; value: boolean; onChange: (value: boolean) => void }) {
  return (
    <Pressable style={styles.switchRow} onPress={() => onChange(!value)} accessibilityRole="switch" accessibilityLabel={label} accessibilityState={{ checked: value }}>
      <AppText variant="label" style={styles.switchLabel}>
        {label}
      </AppText>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.ink, false: colors.tint }} thumbColor={colors.surface} />
    </Pressable>
  );
}

/** One line saying how fast the streamed voice starts, from his own turns. */
function StreamedVoiceNumbers({ report }: { report: Report['realtime'] }) {
  if (report.first_sound_ms_median === null)
    return (
      <AppText variant="caption" tone="muted">
        No streamed sentences yet. Talk a few times to measure it.
      </AppText>
    );
  const verdict = report.met ? 'Target met.' : report.streamed_turns < report.needed_turns ? `${report.needed_turns - report.streamed_turns} more sentences to finish the test.` : 'Slower than the target.';
  return (
    <AppText variant="caption" tone="muted">
      Starts <AppText variant="caption" style={styles.number}>{Math.round(report.first_sound_ms_median)} ms</AppText> after the text appears (middle of {report.streamed_turns}). Target {report.target_ms} ms. {verdict}
    </AppText>
  );
}

/** The lips test results so far, in one or two plain lines. */
function LipsNumbers({ report }: { report: Report['lips_report'] }) {
  const capture = report.capture;
  return (
    <View style={styles.numbers}>
      <AppText variant="caption" tone="muted">
        {capture
          ? `Camera test: ${capture.fps_median ?? 0} frames a second over ${Math.round(capture.seconds / 60)} min, ${capture.seconds_at_24_pct}% of seconds at 24 or more. ${capture.met ? 'Target met.' : 'Target is 24 for 10 minutes.'}`
          : 'Camera test not run yet.'}
      </AppText>
      <AppText variant="caption" tone="muted">
        {report.sync_offsets_ms.length ? `Sound and picture lined up (${Math.round(report.sync_offsets_ms[report.sync_offsets_ms.length - 1])} ms).` : 'Sync check not done yet.'}
      </AppText>
    </View>
  );
}

export default function ExperimentsScreen() {
  const choices = useExperimentChoices();
  const available = useExperimentAvailability();
  const report = useServerData<unknown>('/experiments/report');
  const parsed = report.data ? reportSchema.safeParse(report.data) : null;

  return (
    <Screen>
      <Stack.Screen options={{ title: 'Experiments' }} />
      <AppText tone="muted">These are still being tested. Each one is off until you switch it on, and the rest of the app works the same either way.</AppText>
      {available.realtimeVoice ? (
        <View style={styles.card}>
          <SwitchRow label="Stream my voice" value={choices.streamedVoice} onChange={(streamedVoice) => updateExperiments({ streamedVoice })} />
          <AppText variant="caption" tone="muted">
            Your voice starts while the rest of the sentence is still being made, here and on calls.
          </AppText>
          {report.loading ? <ActivityIndicator color={colors.text} style={styles.spinner} /> : null}
          {report.error ? <ErrorNote message={report.error} onRetry={report.reload} /> : null}
          {parsed?.success ? <StreamedVoiceNumbers report={parsed.data.realtime} /> : null}
        </View>
      ) : null}
      {available.lips ? (
        <View style={styles.card}>
          <SwitchRow label="Use my camera for lip reading" value={choices.lipsCamera} onChange={(lipsCamera) => updateExperiments({ lipsCamera })} />
          <AppText variant="caption" tone="muted">
            The front camera watches your mouth to tell when you are speaking, so your turn ends sooner and other people are ignored. The picture is never shown and never kept.
          </AppText>
          {choices.lipsCamera ? (
            <View style={styles.actions}>
              <Button label="Talk with lips" kind="primary" icon={ScanFace} onPress={() => router.push('/lips')} />
              <Button label="Set up the camera" onPress={() => router.push('/lips-setup')} />
            </View>
          ) : null}
          {parsed?.success ? <LipsNumbers report={parsed.data.lips_report} /> : null}
        </View>
      ) : null}
      {!available.realtimeVoice && !available.lips ? <AppText>No experiments are running on this device.</AppText> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.md, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  switchRow: { minHeight: target.min, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.md },
  switchLabel: { flex: 1 },
  number: { fontVariant: ['tabular-nums'], color: colors.text },
  spinner: { alignSelf: 'flex-start' },
  actions: { gap: space.sm },
  numbers: { gap: space.xs },
});
