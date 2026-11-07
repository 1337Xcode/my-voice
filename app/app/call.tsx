/** The in-call screen (spec 11.6, 13): who and how long, their live captions and his sentences, his Talk controls, Hang up. */
import { router, useLocalSearchParams } from 'expo-router';
import { Keyboard, MessageSquareText, Mic, PhoneOff, Square, X } from 'lucide-react-native';
import { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View, type ScrollViewInstance } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { CallButton } from '@/features/calls/CallButton';
import { PhraseSheet } from '@/features/calls/PhraseSheet';
import { CallKind, CallPhase, useCall } from '@/features/calls/useCall';
import { NumberedOption } from '@/features/talk/NumberedOption';
import { TypeSheet } from '@/features/talk/TypeSheet';
import { useTalk } from '@/features/talk/useTalk';
import { colors, radius, space } from '@/theme';

/** "02:07" from milliseconds. */
function clock(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function statusLine(phase: CallPhase, detail: string | null, connectedAt: number | null, now: number): string {
  if (phase === 'connected' && connectedAt) return clock(now - connectedAt);
  if (phase === 'ended') return 'Call ended';
  if (phase === 'failed') return detail ?? 'The call could not be made.';
  if (phase === 'ringing') return 'ringing…';
  return phase === 'dialling' ? 'calling…' : 'connecting…';
}

/** The call screen route: `/call?callId=…&name=…&kind=app|phone`. */
export default function CallScreen() {
  const params = useLocalSearchParams<{ callId: string; name?: string; kind?: CallKind }>();
  const name = params.name ?? '';
  const call = useCall(params.callId ?? '', params.kind === 'phone' ? 'phone' : 'app');
  const talk = useTalk('call');
  const [now, setNow] = useState(() => Date.now());
  const [sheet, setSheet] = useState<'phrases' | 'type' | null>(null);
  const scroll = useRef<ScrollViewInstance>(null);
  const spoken = talk.state.kind === 'speaking' ? talk.state.text : null;
  const over = call.phase === 'ended' || call.phase === 'failed';
  const { addLine } = call;

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (spoken) addLine('me', spoken);
  }, [spoken, addLine]);

  const { kind } = talk.state;
  const talkLabel = kind === 'listening' ? 'Done' : kind === 'thinking' ? 'Working…' : 'Talk';

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.head} accessibilityLiveRegion="polite">
        <AppText variant="title" numberOfLines={1}>
          {name || 'Call'}
        </AppText>
        <AppText tone="muted">{statusLine(call.phase, call.detail, call.connectedAt, now)}</AppText>
      </View>
      <ScrollView ref={scroll} style={styles.captions} contentContainerStyle={styles.captionsContent} onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}>
        {call.lines.map((line) => (
          <View key={line.id} style={styles.line}>
            <AppText variant="caption" tone="muted">
              {line.who === 'me' ? 'You' : name || 'Them'}
            </AppText>
            <AppText variant={line.who === 'them' ? 'heading' : 'body'} tone={line.who === 'them' ? 'default' : 'muted'}>
              {line.text}
            </AppText>
          </View>
        ))}
      </ScrollView>
      {talk.state.kind === 'pick' ? (
        <View style={styles.panel}>
          {talk.state.candidates.map((c, i) => (
            <NumberedOption key={c.id} index={i + 1} text={c.text} onPress={() => talk.choose(c)} hint="Says this on the call" />
          ))}
        </View>
      ) : null}
      {talk.state.kind === 'again' || talk.state.kind === 'error' || talk.state.kind === 'ignored' ? (
        <View style={[styles.panel, styles.note]} accessibilityRole="alert">
          <AppText>{talk.state.kind === 'error' ? talk.state.message : talk.state.kind === 'ignored' ? "Didn't catch any speech." : "I didn't catch that. Say it again, or type it."}</AppText>
        </View>
      ) : null}
      <View style={styles.grid}>
        <CallButton label={talkLabel} icon={kind === 'listening' ? Square : Mic} active={kind === 'listening'} busy={kind === 'thinking'} disabled={over || !talk.online} onPress={() => void (kind === 'listening' ? talk.done() : talk.talk())} />
        <CallButton label="Phrases" icon={MessageSquareText} disabled={over} onPress={() => setSheet('phrases')} />
        <CallButton label="Type" icon={Keyboard} disabled={over} onPress={() => setSheet('type')} />
      </View>
      <View style={styles.end}>
        {over ? <Button label="Close" icon={X} onPress={() => router.back()} /> : <CallButton label="Hang up" icon={PhoneOff} tone="hangup" onPress={() => void call.hangUp()} />}
      </View>
      <PhraseSheet visible={sheet === 'phrases'} onClose={() => setSheet(null)} onSay={(p) => void talk.sayPhrase(p)} />
      <TypeSheet visible={sheet === 'type'} online={talk.online} onClose={() => setSheet(null)} onSpeak={(text) => void talk.type(text)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  head: { alignItems: 'center', gap: space.xs, paddingHorizontal: space.xl, paddingTop: space.xxl, paddingBottom: space.lg },
  captions: { flex: 1 },
  captionsContent: { flexGrow: 1, justifyContent: 'flex-end', gap: space.lg, paddingHorizontal: space.xl, paddingVertical: space.lg },
  line: { gap: 2 },
  panel: { gap: space.sm, marginHorizontal: space.xl, marginBottom: space.lg },
  note: { padding: space.lg, borderRadius: radius, backgroundColor: colors.tint },
  grid: { flexDirection: 'row', justifyContent: 'center', gap: space.xl, paddingVertical: space.lg },
  end: { alignItems: 'center', paddingTop: space.md, paddingBottom: space.xl },
});
