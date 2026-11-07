/** Talk: the main screen (spec 11.3). One big button at the bottom centre; the middle shows the turn's state. */
import { Link, router } from 'expo-router';
import { Check, Keyboard, ScanFace, Settings, SlidersHorizontal, X } from 'lucide-react-native';
import { MotiView } from 'moti';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { ConnectionBadge } from '@/components/ConnectionBadge';
import { useExperimentAvailability } from '@/features/experiments/ExperimentsSync';
import { useExperimentChoices } from '@/features/experiments/store';
import { stateTransition, useReduceMotion } from '@/features/motion/useReduceMotion';
import { usePhrases } from '@/features/phrases/PhrasesProvider';
import { RoundAction, RoundSpacer } from '@/features/talk/RoundAction';
import { TalkButton, TalkButtonMode } from '@/features/talk/TalkButton';
import { TalkStage } from '@/features/talk/TalkStage';
import { TypeSheet } from '@/features/talk/TypeSheet';
import { Talk, useTalk } from '@/features/talk/useTalk';
import { colors, pill, space, target } from '@/theme';

/** What the big button does in each state. */
function buttonFor(talk: Talk): { mode: TalkButtonMode; label?: string; press: () => void } {
  const { kind } = talk.state;
  if (kind === 'listening') return { mode: 'done', press: () => void talk.done() };
  if (kind === 'thinking') return { mode: 'working', press: () => undefined };
  if (!talk.online) return { mode: 'disabled', press: () => undefined };
  const label = kind === 'pick' || kind === 'again' || kind === 'error' ? 'Say again' : undefined;
  return { mode: 'talk', label, press: () => void talk.talk('talk') };
}

function LearnedNote() {
  const reduce = useReduceMotion();
  return (
    <MotiView from={{ opacity: 0, translateY: reduce ? 0 : -6 }} animate={{ opacity: 1, translateY: 0 }} transition={stateTransition(reduce)} style={styles.learned} accessibilityLiveRegion="polite" accessibilityLabel="Learned">
      <Check size={16} color={colors.inkText} strokeWidth={2.5} />
      <AppText variant="caption" tone="inverse">
        Learned
      </AppText>
    </MotiView>
  );
}

export default function TalkScreen() {
  const talk = useTalk('talk');
  const experiments = useExperimentAvailability();
  const choices = useExperimentChoices();
  const { mostUsed } = usePhrases();
  const [typing, setTyping] = useState(false);
  const button = buttonFor(talk);
  const { kind } = talk.state;
  // While listening (and the first seconds of working it out) the left control cancels; otherwise it opens typing.
  const showType = kind !== 'listening' && !(kind === 'thinking' && !talk.state.slow);

  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <View style={styles.top}>
        <ConnectionBadge />
        {talk.learned ? <LearnedNote /> : null}
        <View style={styles.topRight}>
          {kind === 'idle' && talk.online && experiments.lips ? (
            // Experiment (EXP-SPEC): only on a server with LIPS=1; opens the separate lips screen.
            <Pressable accessibilityRole="button" accessibilityLabel="Talk with lips" accessibilityHint="Opens lip reading with the front camera" onPress={() => router.push(choices.lipsCamera ? '/lips' : '/experiments')} style={({ pressed }) => [styles.tell, pressed && styles.pressed]}>
              <ScanFace size={16} color={colors.text} />
              <AppText variant="caption" unscaled>
                Lips
              </AppText>
            </Pressable>
          ) : null}
          {kind === 'idle' && talk.online ? (
            <Pressable accessibilityRole="button" accessibilityLabel="Tell the app" accessibilityHint="Say a settings change, like make the text bigger" onPress={() => void talk.talk('tell')} style={({ pressed }) => [styles.tell, pressed && styles.pressed]}>
              <SlidersHorizontal size={16} color={colors.text} />
              <AppText variant="caption" unscaled>
                Tell the app
              </AppText>
            </Pressable>
          ) : null}
          <Link href="/settings" asChild>
          <Pressable accessibilityRole="button" accessibilityLabel="Settings" hitSlop={8} style={styles.gear}>
            <Settings size={24} color={colors.text} strokeWidth={1.8} />
            </Pressable>
          </Link>
        </View>
      </View>
      <View style={styles.stage}>
        <TalkStage talk={talk} phrases={mostUsed(6)} />
      </View>
      <View style={styles.bottom}>
        {showType ? <RoundAction label="Type" icon={Keyboard} onPress={() => setTyping(true)} /> : <RoundAction label="Cancel" icon={X} onPress={() => void talk.cancel()} />}
        <TalkButton mode={button.mode} label={button.label} onPress={button.press} />
        {kind === 'thinking' && talk.state.slow ? <RoundAction label="Cancel" icon={X} onPress={() => void talk.cancel()} /> : <RoundSpacer />}
      </View>
      {kind === 'listening' ? (
        <AppText variant="caption" tone="muted" style={styles.hint}>
          Tap when you have finished. No rush.
        </AppText>
      ) : null}
      <TypeSheet visible={typing} online={talk.online} onClose={() => setTyping(false)} onSpeak={(text) => void talk.type(text)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.md, paddingHorizontal: space.xl, minHeight: target.min + 8 },
  gear: { width: target.min, height: target.min, alignItems: 'center', justifyContent: 'center', marginRight: -space.md },
  stage: { flex: 1, paddingHorizontal: space.xl, paddingTop: space.md },
  bottom: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'center', paddingTop: space.xl, paddingBottom: space.md },
  hint: { textAlign: 'center', paddingBottom: space.md },
  topRight: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  tell: { flexDirection: 'row', alignItems: 'center', gap: space.xs, minHeight: 36, paddingHorizontal: space.md, borderRadius: pill, backgroundColor: colors.tint },
  pressed: { opacity: 0.7 },
  learned: { flexDirection: 'row', alignItems: 'center', gap: space.xs, paddingHorizontal: space.md, paddingVertical: space.xs, borderRadius: pill, backgroundColor: colors.ink },
});
