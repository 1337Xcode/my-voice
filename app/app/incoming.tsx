/** Someone is calling him through his call link: the name large, Decline and Accept, like the phone's own incoming call. */
import { router, useLocalSearchParams } from 'expo-router';
import { Phone, PhoneOff } from 'lucide-react-native';
import { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { buzz } from '@/features/talk/haptics';
import { colors, space } from '@/theme';

const SIZE = 80;

function Answer({ label, fill, onPress, decline = false }: { label: string; fill: string; onPress: () => void; decline?: boolean }) {
  const Icon = decline ? PhoneOff : Phone;
  return (
    <View style={styles.answer}>
      <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={({ pressed }) => [styles.circle, { backgroundColor: fill }, pressed && styles.pressed]}>
        <Icon size={34} color={colors.accentText} fill={decline ? 'transparent' : colors.accentText} strokeWidth={2.2} />
      </Pressable>
      <AppText variant="label" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </AppText>
    </View>
  );
}

export default function IncomingCallScreen() {
  const { callId, name } = useLocalSearchParams<{ callId: string; name?: string }>();
  const { socket } = useConnection();

  useEffect(() => buzz('listen'), []);

  // If the caller gives up first, the call ends and this screen closes.
  useEffect(
    () =>
      socket?.onMessage((message) => {
        if (message.type === 'call_status' && message.call_id === callId && (message.state === 'ended' || message.state === 'failed')) router.back();
      }),
    [socket, callId],
  );

  const accept = () => {
    socket?.send({ type: 'answer_call', call_id: callId });
    router.replace({ pathname: '/call', params: { callId, name: name ?? '', kind: 'app' } });
  };
  const decline = () => {
    socket?.send({ type: 'decline_call', call_id: callId });
    router.back();
  };

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.head} accessibilityLiveRegion="assertive">
        <AppText variant="title" size={36}>
          {name || 'Someone'}
        </AppText>
        <AppText tone="muted">My Voice call</AppText>
      </View>
      <View style={styles.row}>
        <Answer label="Decline" fill={colors.accent} onPress={decline} decline />
        <Answer label="Accept" fill={colors.go} onPress={accept} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, justifyContent: 'space-between', backgroundColor: colors.background },
  head: { alignItems: 'center', gap: space.sm, paddingTop: space.xxxl * 2, paddingHorizontal: space.xl },
  row: { flexDirection: 'row', justifyContent: 'space-evenly', paddingBottom: space.xxxl * 1.5 },
  answer: { alignItems: 'center', gap: space.sm },
  circle: { width: SIZE, height: SIZE, borderRadius: SIZE / 2, alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.8 },
});
