/** The big round button at the bottom centre: Talk, Done while listening, a soft spinner while working it out. */
import { Mic, Square } from 'lucide-react-native';
import { MotiView } from 'moti';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { stateTransition, useReduceMotion } from '@/features/motion/useReduceMotion';
import { colors, space, target } from '@/theme';

export type TalkButtonMode = 'talk' | 'done' | 'working' | 'disabled';

const labels: Record<TalkButtonMode, string> = { talk: 'Talk', done: 'Done', working: 'Working it out…', disabled: 'Talk' };

export function TalkButton({ mode, label, onPress }: { mode: TalkButtonMode; label?: string; onPress: () => void }) {
  const reduce = useReduceMotion();
  const text = label ?? labels[mode];
  const inactive = mode === 'working' || mode === 'disabled';
  const fill = mode === 'working' ? colors.working : mode === 'disabled' ? colors.tint : colors.accent;
  return (
    <View style={styles.wrap}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={text}
        accessibilityHint={mode === 'talk' ? 'Starts listening' : mode === 'done' ? 'Ends what you are saying' : undefined}
        accessibilityState={{ disabled: inactive, busy: mode === 'working' }}
        disabled={inactive}
        onPress={onPress}>
        {({ pressed }) => (
          <MotiView animate={{ backgroundColor: fill, scale: pressed && !reduce ? 0.96 : 1 }} transition={stateTransition(reduce)} style={styles.circle}>
            {mode === 'working' ? <ActivityIndicator size="large" color={colors.accent} /> : null}
            {mode === 'done' ? <Square size={36} color={colors.accentText} fill={colors.accentText} /> : null}
            {mode === 'talk' || mode === 'disabled' ? <Mic size={44} color={mode === 'talk' ? colors.accentText : colors.muted} strokeWidth={2} /> : null}
          </MotiView>
        )}
      </Pressable>
      <AppText variant="label" tone={mode === 'disabled' ? 'muted' : 'default'} importantForAccessibility="no" accessibilityElementsHidden>
        {text}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', gap: space.sm },
  circle: { width: target.talk, height: target.talk, borderRadius: target.talk / 2, alignItems: 'center', justifyContent: 'center' },
});
