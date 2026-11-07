/** Haptic feedback on Listening start, result, Learned and errors (spec 11.10); silent on web. */
import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

type Moment = 'listen' | 'result' | 'learned' | 'error';

export function buzz(moment: Moment): void {
  if (Platform.OS === 'web') return;
  const done = () => undefined;
  if (moment === 'listen') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(done);
  if (moment === 'result') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(done);
  if (moment === 'learned') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(done);
  if (moment === 'error') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(done);
}
