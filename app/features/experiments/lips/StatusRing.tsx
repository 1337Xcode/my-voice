/** The lips status (EXP-SPEC 4.2): grey no face, amber mouth unclear, green mouth visible, a soft pulse when his lips move. */
import { MotiView } from 'moti';
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { stateTransition, useReduceMotion } from '@/features/motion/useReduceMotion';
import { colors, pill, space } from '@/theme';
import type { LipQuality, LipStatus } from './LipCamera';
import type { LipsPhase } from './useLips';

// Status colours, used only for this status. Each is paired with words, so meaning never rests on colour alone.
const ring = { grey: colors.faint, amber: '#A15C07', green: colors.go } as const;

const guidance: Record<LipQuality, string> = {
  no_face: 'Move the phone so I can see your mouth',
  turned: 'Turn to face the phone',
  far: 'Bring the phone a little closer',
  dark: 'A bit more light would help',
  good: 'I can see your mouth',
};

const phaseText: Partial<Record<LipsPhase, string>> = {
  needs_consent: 'Camera off',
  connecting: 'Connecting…',
  starting: 'Getting the camera ready…',
  paused: 'Camera paused',
  error: 'Camera stopped',
};

/** What the ring says and which colour it is in, for a phase and the latest camera status. */
export function ringState(phase: LipsPhase, status: LipStatus | null): { colour: keyof typeof ring; text: string } {
  if (phase !== 'on' || !status) return { colour: 'grey', text: phaseText[phase] ?? 'Getting the camera ready…' };
  if (status.quality === 'no_face') return { colour: 'grey', text: guidance.no_face };
  return { colour: status.quality === 'good' ? 'green' : 'amber', text: guidance[status.quality] };
}

export function StatusRing({ phase, status }: { phase: LipsPhase; status: LipStatus | null }) {
  const reduce = useReduceMotion();
  const { colour, text } = ringState(phase, status);
  const pulsing = !reduce && phase === 'on' && Boolean(status?.moving);
  return (
    <View style={styles.row} accessibilityRole="text" accessibilityLabel={`Camera: ${text}`} accessibilityLiveRegion="polite">
      <View style={styles.ringBox}>
        <MotiView
          animate={{ scale: pulsing ? 1.25 : 1, opacity: pulsing ? 0.35 : 0 }}
          transition={stateTransition(reduce)}
          style={[styles.halo, { backgroundColor: ring[colour] }]}
        />
        <View style={[styles.ring, { borderColor: ring[colour] }]}>
          <View style={[styles.dot, { backgroundColor: ring[colour] }]} />
        </View>
      </View>
      <AppText variant="label" style={styles.text}>
        {text}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.lg, paddingVertical: space.md, borderRadius: pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  ringBox: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  halo: { position: 'absolute', width: 28, height: 28, borderRadius: 14 },
  ring: { width: 24, height: 24, borderRadius: 12, borderWidth: 3, alignItems: 'center', justifyContent: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { flex: 1 },
});
