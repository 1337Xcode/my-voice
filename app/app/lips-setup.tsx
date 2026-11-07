/**
 * Set up the camera for lip reading (EXP-SPEC 4.2, 4.4, 4.5): place the phone using a drawn outline (never the camera's
 * picture), line up sound and picture with "pa pa pa", and run the camera test.
 */
import { Stack } from 'expo-router';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import Svg, { Ellipse, Rect } from 'react-native-svg';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import type { LipStatus } from '@/features/experiments/lips/LipCamera';
import { StatusRing } from '@/features/experiments/lips/StatusRing';
import { useCaptureTest, type CaptureTestState } from '@/features/experiments/lips/useCaptureTest';
import { useLips } from '@/features/experiments/lips/useLips';
import { useSyncCheck, type SyncState } from '@/features/experiments/lips/useSyncCheck';
import { colors, radius, space } from '@/theme';

// The outline's frame has the camera's 4:3 shape, upright.
const FRAME_W = 180;
const FRAME_H = 240;

/** Where his face sits in the camera's view, drawn as a rounded box with a mouth that opens as his does. */
function FaceOutline({ status }: { status: LipStatus | null }) {
  const box = status?.box;
  const good = status?.quality === 'good';
  // The front camera's picture is not mirrored; flip x so moving left moves the outline left, like a mirror.
  const x = box ? (1 - box.x - box.w) * FRAME_W : 0;
  const mouthY = box ? (box.y + box.h * 0.8) * FRAME_H : 0;
  return (
    <View style={styles.outline} accessibilityRole="image" accessibilityLabel={box ? (good ? 'Your face is well placed' : 'Your face is in view') : 'No face in view'}>
      <Svg width={FRAME_W} height={FRAME_H}>
        <Rect x={1} y={1} width={FRAME_W - 2} height={FRAME_H - 2} rx={16} fill={colors.surface} stroke={colors.border} strokeWidth={2} />
        {box ? (
          <>
            <Rect x={x} y={box.y * FRAME_H} width={box.w * FRAME_W} height={box.h * FRAME_H} rx={box.w * FRAME_W * 0.35} fill="none" stroke={good ? colors.go : '#A15C07'} strokeWidth={3} />
            <Ellipse cx={x + (box.w * FRAME_W) / 2} cy={mouthY} rx={box.w * FRAME_W * 0.18} ry={Math.max(2, (status?.mouthAspect ?? 0) * box.w * FRAME_W * 0.4)} fill={colors.text} />
          </>
        ) : null}
      </Svg>
    </View>
  );
}

function SyncSection({ sync, ready }: { sync: { state: SyncState; run: () => void }; ready: boolean }) {
  const { state } = sync;
  return (
    <View style={styles.card}>
      <AppText variant="heading">Line up sound and picture</AppText>
      <AppText tone="muted">Takes 10 seconds. When it starts, say &ldquo;pa&rdquo; five times, slowly: pa, pa, pa, pa, pa.</AppText>
      {state.kind === 'recording' ? <AppText variant="title">Say pa… {state.secondsLeft}</AppText> : null}
      {state.kind === 'measuring' ? <ActivityIndicator color={colors.text} style={styles.left} /> : null}
      {state.kind === 'done' ? <AppText variant="label">Done. Sound and picture are lined up ({Math.round(state.offsetMs)} ms).</AppText> : null}
      {state.kind === 'failed' ? <ErrorNote message={state.message} /> : null}
      {state.kind === 'idle' || state.kind === 'done' || state.kind === 'failed' ? (
        <Button label={state.kind === 'idle' ? 'Start' : 'Do it again'} kind={state.kind === 'idle' ? 'primary' : 'outline'} disabled={!ready} onPress={sync.run} style={styles.left} />
      ) : null}
    </View>
  );
}

function CaptureSection({ test, ready }: { test: { state: CaptureTestState; run: (minutes: number) => void; stop: () => void }; ready: boolean }) {
  const { state } = test;
  return (
    <View style={styles.card}>
      <AppText variant="heading">Camera test</AppText>
      <AppText tone="muted">Runs the camera, the microphone and your voice together, to check the phone keeps up. Your voice plays a phrase every 20 seconds.</AppText>
      {state.kind === 'running' ? (
        <View style={styles.numbers}>
          <AppText variant="label">
            {Math.floor(state.elapsedS / 60)}:{String(state.elapsedS % 60).padStart(2, '0')} of {state.totalS / 60}:00
          </AppText>
          <AppText tone="muted">
            {state.fps} frames a second · microphone {state.micOk ? 'steady' : 'had a gap'}
          </AppText>
          <Button label="Stop" onPress={test.stop} style={styles.left} />
        </View>
      ) : null}
      {state.kind === 'saving' ? <ActivityIndicator color={colors.text} style={styles.left} /> : null}
      {state.kind === 'done' ? (
        <AppText variant="label">
          {state.verdict.met ? 'Passed. ' : state.verdict.seconds < 600 ? 'Finished. ' : 'Not quite. '}
          {state.verdict.fps_median ?? 0} frames a second, {state.verdict.seconds_at_24_pct}% of seconds at 24 or more, {state.verdict.stalls} stalls, {state.verdict.mic_gaps} microphone gaps.
          {state.verdict.seconds < 600 ? ' The full test is 10 minutes.' : ''}
        </AppText>
      ) : null}
      {state.kind === 'failed' ? <ErrorNote message={state.message} /> : null}
      {state.kind !== 'running' && state.kind !== 'saving' ? (
        <View style={styles.row}>
          <Button label="Run for 10 minutes" kind="primary" disabled={!ready} onPress={() => test.run(10)} />
          <Button label="1 minute" disabled={!ready} onPress={() => test.run(1)} />
        </View>
      ) : null}
    </View>
  );
}

export default function LipsSetupScreen() {
  const lips = useLips();
  const sync = useSyncCheck();
  const test = useCaptureTest(lips.camera);
  const ready = lips.phase === 'on';
  return (
    <Screen>
      <Stack.Screen options={{ title: 'Set up the camera' }} />
      <View style={styles.card}>
        <AppText variant="heading">Place the phone</AppText>
        <AppText tone="muted">Stand it 30 to 50 cm away, level with your face. The outline turns green when your mouth is in view.</AppText>
        <FaceOutline status={lips.status} />
        <StatusRing phase={lips.phase} status={lips.status} />
        {lips.phase === 'error' && lips.error ? <ErrorNote message={lips.error} onRetry={lips.retry} /> : null}
      </View>
      <SyncSection sync={sync} ready={ready} />
      <CaptureSection test={test} ready={ready} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.md, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  outline: { alignSelf: 'center' },
  left: { alignSelf: 'flex-start' },
  numbers: { gap: space.xs },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
});
