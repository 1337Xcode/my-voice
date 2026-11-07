/** The page family open from his call link: one Call button, then his sentences very large and his voice. No login. */
import { useLocalSearchParams } from 'expo-router';
import { Phone, PhoneOff } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { ErrorNote } from '@/components/ErrorNote';
import { GuestPhase, PeerState, useGuestCall } from '@/features/calls/useGuestCall';
import { LevelBars } from '@/features/talk/LevelBars';
import { colors, fonts, radius, space, target } from '@/theme';

const peerText: Record<PeerState, string | null> = {
  listening: "He's speaking…",
  thinking: 'Working it out…',
  choosing: 'Choosing the right words…',
  idle: null,
};

/** "02:07" from milliseconds. */
function clock(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function statusOf(phase: GuestPhase, connectedAt: number | null, now: number): string {
  if (phase === 'connected' && connectedAt) return clock(now - connectedAt);
  if (phase === 'ringing') return 'ringing…';
  if (phase === 'ended') return 'Call ended';
  if (phase === 'failed') return 'The call did not go through';
  return 'calling…';
}

function RoundButton({ label, hangUp = false, onPress }: { label: string; hangUp?: boolean; onPress: () => void }) {
  const Icon = hangUp ? PhoneOff : Phone;
  return (
    <View style={styles.roundWrap}>
      <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={({ pressed }) => [styles.round, { backgroundColor: hangUp ? colors.accent : colors.go }, pressed && styles.pressed]}>
        <Icon size={hangUp ? 38 : 44} color={colors.accentText} fill={hangUp ? 'transparent' : colors.accentText} strokeWidth={2.2} />
      </Pressable>
      <AppText variant="label" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </AppText>
    </View>
  );
}

export default function GuestCallPage() {
  const { code = '' } = useLocalSearchParams<{ code: string }>();
  const call = useGuestCall(code);
  const [name, setName] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const inCall = call.phase !== 'ready' && call.phase !== 'ended' && call.phase !== 'failed';
  const latest = call.sentences[call.sentences.length - 1];
  const earlier = call.sentences.slice(-5, -1);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  if (call.phase === 'ready' || (!inCall && call.sentences.length === 0)) {
    return (
      <SafeAreaView style={styles.screen}>
        <View style={styles.start}>
          <View style={styles.head}>
            <AppText variant="title" size={34}>
              My Voice call
            </AppText>
            <AppText tone="muted" style={styles.code}>
              Code {code}
            </AppText>
          </View>
          {call.phase === 'failed' ? <ErrorNote message={call.detail ?? 'The call did not go through. Try again.'} /> : null}
          {call.phase === 'ended' ? (
            <AppText variant="heading" style={styles.centreText}>
              Call ended
            </AppText>
          ) : null}
          <View style={styles.field}>
            <AppText variant="caption" tone="muted">
              Your first name
            </AppText>
            <TextInput accessibilityLabel="Your first name" value={name} onChangeText={setName} autoComplete="given-name" style={styles.input} placeholder="So he knows who is calling" placeholderTextColor={colors.faint} />
          </View>
          <RoundButton label={call.phase === 'ready' ? 'Call' : 'Call again'} onPress={() => void call.call(name)} />
          <AppText variant="caption" tone="muted" style={styles.centreText}>
            Allow the microphone when your browser asks.
          </AppText>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.head} accessibilityLiveRegion="polite">
        <AppText variant="heading">{statusOf(call.phase, call.connectedAt, now)}</AppText>
        <AppText tone="muted">{peerText[call.peer] ?? (call.phase === 'connected' ? 'Talk normally.' : ' ')}</AppText>
      </View>
      <ScrollView style={styles.flex} contentContainerStyle={styles.sentences}>
        {earlier.map((text, index) => (
          <AppText key={`${index}-${text}`} variant="heading" tone="faint">
            {text}
          </AppText>
        ))}
        {latest ? (
          <View style={styles.latest}>
            <AppText variant="sentence" accessibilityLiveRegion="assertive">
              {latest}
            </AppText>
          </View>
        ) : null}
      </ScrollView>
      {inCall ? <LevelBars levels={call.levels} /> : null}
      <View style={styles.bottom}>{inCall ? <RoundButton label="Hang up" hangUp onPress={call.hangUp} /> : <RoundButton label="Call again" onPress={() => void call.call(name)} />}</View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  start: { flex: 1, justifyContent: 'center', gap: space.xxl, paddingHorizontal: space.xl },
  head: { alignItems: 'center', gap: space.xs, paddingHorizontal: space.xl, paddingTop: space.xl },
  code: { fontVariant: ['tabular-nums'], letterSpacing: 1 },
  centreText: { textAlign: 'center' },
  field: { gap: space.xs },
  input: { minHeight: target.min + 4, paddingHorizontal: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, fontFamily: fonts.medium, fontSize: 18, color: colors.text },
  roundWrap: { alignItems: 'center', gap: space.sm },
  round: { width: target.talk, height: target.talk, borderRadius: target.talk / 2, alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.8 },
  sentences: { flexGrow: 1, justifyContent: 'flex-end', gap: space.lg, padding: space.xl },
  latest: { padding: space.xl, borderRadius: 28, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  bottom: { alignItems: 'center', paddingVertical: space.xl },
});
