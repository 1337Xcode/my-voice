/**
 * Talk with lips (EXP-SPEC 11): the Talk screen's turn, with the front camera watching his mouth. The camera's picture
 * is never shown; the status line says whether his mouth is in view, and the middle shows what he said.
 */
import { router, Stack } from 'expo-router';
import { Keyboard, X } from 'lucide-react-native';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { StatusRing } from '@/features/experiments/lips/StatusRing';
import { useLips } from '@/features/experiments/lips/useLips';
import { usePhrases } from '@/features/phrases/PhrasesProvider';
import { RoundAction, RoundSpacer } from '@/features/talk/RoundAction';
import { TalkButton, TalkButtonMode } from '@/features/talk/TalkButton';
import { TalkStage } from '@/features/talk/TalkStage';
import { TypeSheet } from '@/features/talk/TypeSheet';
import { Talk, useTalk } from '@/features/talk/useTalk';
import { colors, space } from '@/theme';

/** What the big button does in each state (the same as on Talk). */
function buttonFor(talk: Talk): { mode: TalkButtonMode; label?: string; press: () => void } {
  const { kind } = talk.state;
  if (kind === 'listening') return { mode: 'done', press: () => void talk.done() };
  if (kind === 'thinking') return { mode: 'working', press: () => undefined };
  if (!talk.online) return { mode: 'disabled', press: () => undefined };
  const label = kind === 'pick' || kind === 'again' || kind === 'error' ? 'Say again' : undefined;
  return { mode: 'talk', label, press: () => void talk.talk('talk') };
}

export default function LipsScreen() {
  const lips = useLips();
  const talk = useTalk('talk');
  const { mostUsed } = usePhrases();
  const [typing, setTyping] = useState(false);
  const button = buttonFor(talk);
  const { kind } = talk.state;
  const showType = kind !== 'listening' && !(kind === 'thinking' && !talk.state.slow);

  return (
    <SafeAreaView edges={['bottom']} style={styles.screen}>
      <Stack.Screen options={{ title: 'Talk with lips' }} />
      <View style={styles.top}>
        <StatusRing phase={lips.phase} status={lips.status} />
        {lips.phase === 'needs_consent' ? (
          <View style={styles.consent}>
            <AppText>Turn on lip reading in Experiments first. The camera&apos;s picture is never shown and never kept.</AppText>
            <Button label="Open Experiments" onPress={() => router.replace('/experiments')} style={styles.left} />
          </View>
        ) : null}
        {lips.phase === 'error' && lips.error ? <ErrorNote message={lips.error} onRetry={lips.retry} /> : null}
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
  top: { paddingHorizontal: space.xl, paddingTop: space.md, gap: space.md },
  consent: { gap: space.md },
  left: { alignSelf: 'flex-start' },
  stage: { flex: 1, paddingHorizontal: space.xl, paddingTop: space.md },
  bottom: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'center', paddingTop: space.xl, paddingBottom: space.md },
  hint: { textAlign: 'center', paddingBottom: space.md },
});
