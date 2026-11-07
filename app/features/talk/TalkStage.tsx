/** The middle of Talk: what he and the listener see in each state of a turn (spec 11.3). */
import { CircleAlert, MicOff, Volume2, VolumeX, WifiOff } from 'lucide-react-native';
import { MotiView } from 'moti';
import { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { stateTransition, useReduceMotion } from '@/features/motion/useReduceMotion';
import type { Phrase } from '@/features/phrases/PhrasesProvider';
import { PhraseChips } from '@/features/phrases/PhraseChips';
import { useSettings } from '@/features/settings/SettingsProvider';
import { ProposalCard } from '@/features/tell/ProposalCard';
import { colors, pill, radius, space } from '@/theme';
import { LevelBars } from './LevelBars';
import { NumberedOption } from './NumberedOption';
import { SentenceCard } from './SentenceCard';
import type { Talk, TalkState, VoiceState } from './useTalk';

/** A soft panel that fades in when the state changes. */
function Panel({ children, label }: { children: ReactNode; label?: string }) {
  const reduce = useReduceMotion();
  return (
    <MotiView from={{ opacity: 0 }} animate={{ opacity: 1 }} transition={stateTransition(reduce)} style={styles.panel} accessibilityLabel={label} accessibilityLiveRegion="polite">
      {children}
    </MotiView>
  );
}

function Listening({ talk, partial }: { talk: Talk; partial: string }) {
  const { settings } = useSettings();
  return (
    <Panel label="Listening">
      {talk.noisy ? (
        <View style={styles.noisy} accessibilityRole="text" accessibilityLabel="Noisy here">
          <Volume2 size={16} color={colors.text} />
          <AppText variant="caption">Noisy here</AppText>
        </View>
      ) : null}
      <LevelBars levels={talk.levels} />
      <View style={styles.centred}>
        <AppText variant="heading">Listening. Talk when you&apos;re ready.</AppText>
        {settings.dev.partials && partial ? <AppText tone="muted">{partial}</AppText> : null}
      </View>
    </Panel>
  );
}

function Thinking({ talk, slow }: { talk: Talk; slow: boolean }) {
  return (
    <Panel label={slow ? 'Taking a moment' : 'Working it out'}>
      <LevelBars levels={talk.levels} frozen />
      <View style={styles.centred}>
        <AppText variant="heading">{slow ? 'Taking a moment' : 'Working it out…'}</AppText>
      </View>
    </Panel>
  );
}

/** The line at the top of the sentence card saying whether it is speaking, waiting, or failed. */
function VoiceStatus({ voice, error }: { voice: VoiceState; error: string | null }) {
  if (voice === 'failed')
    return (
      <View style={styles.statusRow} accessibilityRole="alert">
        <CircleAlert size={18} color={colors.accent} />
        <AppText variant="caption" style={styles.flex}>
          {error ?? "The voice didn't play."}
        </AppText>
      </View>
    );
  const text = { confirm: 'Check it, then tap Speak it', waiting: 'Getting the voice…', playing: 'Speaking', done: 'Said', remote: 'Said on the call' }[voice];
  return (
    <View style={styles.statusRow}>
      {voice === 'waiting' ? <ActivityIndicator size="small" color={colors.muted} /> : voice === 'confirm' ? <VolumeX size={18} color={colors.muted} /> : <Volume2 size={18} color={colors.muted} />}
      <AppText variant="caption" tone="muted">
        {text}
      </AppText>
    </View>
  );
}

function Speaking({ talk, state }: { talk: Talk; state: Extract<TalkState, { kind: 'speaking' }> }) {
  const confirm = state.voice === 'confirm';
  return (
    <View style={styles.speaking}>
      <SentenceCard text={state.text} status={<VoiceStatus voice={state.voice} error={state.voiceError} />} />
      <View style={styles.actions}>
        {confirm ? <Button label="Speak it" kind="primary" onPress={talk.confirm} style={styles.flex} /> : <Button label="Replay" onPress={() => void talk.replay()} disabled={state.voice === 'waiting'} style={styles.flex} />}
        {state.turnId ? <Button label="That's wrong" onPress={talk.reject} style={styles.flex} /> : <Button label="Close" onPress={talk.dismiss} style={styles.flex} />}
      </View>
    </View>
  );
}

function Pick({ talk, state }: { talk: Talk; state: Extract<TalkState, { kind: 'pick' }> }) {
  return (
    <View style={styles.list}>
      <AppText variant="title" accessibilityRole="header">
        {state.rejected ? 'Was it one of these?' : 'Which did you mean?'}
      </AppText>
      {state.candidates.map((candidate, index) => (
        <NumberedOption key={candidate.id} index={index + 1} text={candidate.text} onPress={() => talk.choose(candidate)} />
      ))}
    </View>
  );
}

function Again({ talk, state }: { talk: Talk; state: Extract<TalkState, { kind: 'again' }> }) {
  return (
    <View style={styles.list}>
      <View style={styles.gapSm}>
        <AppText variant="title" accessibilityRole="header">
          {state.afterReject ? 'Sorry about that.' : 'I didn’t catch that.'}
        </AppText>
        <AppText tone="muted">Say it again, or type it.</AppText>
      </View>
      {state.guess ? (
        <Pressable accessibilityRole="button" accessibilityLabel={`Best guess: ${state.guess.text}`} accessibilityHint="Speaks this guess" onPress={() => talk.choose(state.guess!)} style={styles.guess}>
          <AppText variant="caption" tone="faint">
            Best guess
          </AppText>
          <AppText tone="faint">{state.guess.text}</AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

function Note({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <Panel label={text}>
      <View style={styles.centred}>
        {icon}
        <AppText variant="heading">{text}</AppText>
      </View>
    </Panel>
  );
}

/** Idle: the offline card when needed, the last few sentences, and his most-used phrases. */
function Idle({ talk, phrases, onSay }: { talk: Talk; phrases: Phrase[]; onSay: (phrase: Phrase) => void }) {
  const recent = talk.turns.slice(-3);
  return (
    <View style={styles.idle}>
      {talk.status === 'offline' ? (
        <View style={styles.offline} accessibilityRole="alert">
          <WifiOff size={22} color={colors.text} />
          <AppText style={styles.flex}>You&apos;re offline — talk needs internet. Your saved phrases still work.</AppText>
        </View>
      ) : null}
      {talk.status === 'unauthorised' || talk.status === 'unconfigured' ? (
        <View style={styles.offline} accessibilityRole="alert">
          <CircleAlert size={22} color={colors.accent} />
          <AppText style={styles.flex}>{talk.status === 'unauthorised' ? 'The app token is wrong. Check it in Settings, under Developer.' : 'The speech server is not set. Add it in Settings, under Developer.'}</AppText>
        </View>
      ) : null}
      {recent.length ? (
        <View style={styles.strip} accessibilityLabel="Recent sentences">
          {recent.map((turn) => (
            <AppText key={turn.id} tone="faint" numberOfLines={1}>
              {turn.text}
            </AppText>
          ))}
        </View>
      ) : null}
      <View style={styles.flexEnd}>
        <PhraseChips phrases={phrases} onSay={onSay} />
      </View>
    </View>
  );
}

export function TalkStage({ talk, phrases }: { talk: Talk; phrases: Phrase[] }) {
  const { state } = talk;
  switch (state.kind) {
    case 'listening':
      return <Listening talk={talk} partial={state.partial} />;
    case 'thinking':
      return <Thinking talk={talk} slow={state.slow} />;
    case 'speaking':
      return <Speaking talk={talk} state={state} />;
    case 'pick':
      return <Pick talk={talk} state={state} />;
    case 'again':
      return <Again talk={talk} state={state} />;
    case 'proposal':
      return <ProposalCard changes={state.changes} heard={state.heard} onDone={talk.dismiss} onTryAgain={() => void talk.talk('tell')} />;
    case 'ignored':
      return <Note icon={<MicOff size={28} color={colors.muted} />} text="Didn't catch any speech" />;
    case 'error':
      return (
        <View style={styles.idle}>
          <View style={styles.offline} accessibilityRole="alert">
            <CircleAlert size={22} color={colors.accent} />
            <AppText style={styles.flex}>{state.message}</AppText>
          </View>
          <View style={styles.flexEnd}>
            <PhraseChips phrases={phrases} onSay={(p) => void talk.sayPhrase(p)} />
          </View>
        </View>
      );
    default:
      return <Idle talk={talk} phrases={phrases} onSay={(p) => void talk.sayPhrase(p)} />;
  }
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  flexEnd: { flex: 1, justifyContent: 'flex-end' },
  gapSm: { gap: space.sm },
  panel: { flex: 1, justifyContent: 'center', gap: space.xl, padding: space.xl, borderRadius: 28, backgroundColor: colors.tint },
  centred: { alignItems: 'center', gap: space.md },
  noisy: { position: 'absolute', top: space.lg, right: space.lg, flexDirection: 'row', alignItems: 'center', gap: space.xs, paddingHorizontal: space.md, paddingVertical: space.xs, borderRadius: pill, backgroundColor: colors.surface },
  speaking: { flex: 1, gap: space.lg },
  actions: { flexDirection: 'row', gap: space.md },
  list: { flex: 1, gap: space.md, justifyContent: 'center' },
  guess: { gap: space.xs, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, borderStyle: 'dashed' },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  idle: { flex: 1, gap: space.xl },
  offline: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.lg, borderRadius: radius, backgroundColor: colors.tint },
  strip: { gap: space.xs },
});
