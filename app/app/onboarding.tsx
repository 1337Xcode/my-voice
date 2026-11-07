/** First run: seven short steps, each skippable, resumable from Teach where he left off. */
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Screen } from '@/components/Screen';
import { STEPS, useOnboardingProgress, type Step } from '@/features/onboarding/onboardingProgress';
import { PhraseRecordingStep } from '@/features/onboarding/PhraseRecordingStep';
import { PhrasesStep } from '@/features/onboarding/PhrasesStep';
import { TestSentencesStep } from '@/features/onboarding/TestSentencesStep';
import { DoneStep, TrainStep } from '@/features/onboarding/TrainStep';
import { WelcomeStep } from '@/features/onboarding/WelcomeStep';
import { saveServerSetting } from '@/features/teach/teachApi';
import { VoicePicker } from '@/features/settings/VoicePicker';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, space } from '@/theme';

/** Step 2: the shared voice list; his choice is sent to the server when he continues. */
function VoiceStep({ onNext }: { onNext: () => void }) {
  const { settings } = useSettings();
  const next = () => {
    // The socket's hello also carries the voice; this saves it for phrase audio right away.
    if (settings.voiceId) void saveServerSetting(settings, { voice_id: settings.voiceId }).catch(() => undefined);
    onNext();
  };
  return (
    <View style={styles.step}>
      <AppText variant="title" accessibilityRole="header">
        Pick a voice
      </AppText>
      <AppText tone="muted">Play each one, then choose the voice that will speak for you.</AppText>
      <VoicePicker />
      <Button kind="primary" label="Continue" onPress={next} />
    </View>
  );
}

export default function OnboardingScreen() {
  const params = useLocalSearchParams<{ step?: string }>();
  const { progress, save } = useOnboardingProgress();
  const [chosen, setStep] = useState<Step | null>(null);
  // Start where the link asked, else where he left off.
  const step = chosen ?? STEPS.find((s) => s === params.step) ?? progress?.step ?? null;

  const go = (next: Step) => {
    setStep(next);
    save({ step: next, seen: true, ...(next === 'done' ? { finished: true } : {}) });
  };
  const advance = () => {
    if (step) go(STEPS[Math.min(STEPS.indexOf(step) + 1, STEPS.length - 1)]);
  };
  const close = () => {
    save({ seen: true });
    if (router.canGoBack()) router.back();
    else router.replace('/');
  };
  const finish = () => {
    save({ seen: true, finished: true, step: 'done' });
    router.replace('/');
  };

  if (!step) return <Screen>{null}</Screen>;
  const index = STEPS.indexOf(step);

  return (
    <SafeAreaView edges={['top']} style={styles.fill}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.top}>
        <AppText variant="caption" tone="muted" accessibilityLabel={`Step ${index + 1} of ${STEPS.length}`}>
          {index + 1} of {STEPS.length}
        </AppText>
        {step !== 'done' ? <Button kind="quiet" label="Finish later" onPress={close} /> : null}
      </View>
      <Screen>
        {step === 'welcome' ? <WelcomeStep onAgree={advance} /> : null}
        {step === 'voice' ? <VoiceStep onNext={advance} /> : null}
        {step === 'phrases' ? <PhrasesStep onNext={advance} /> : null}
        {step === 'test' ? <TestSentencesStep onNext={advance} /> : null}
        {step === 'record' ? <PhraseRecordingStep onNext={advance} /> : null}
        {step === 'train' ? <TrainStep onNext={advance} /> : null}
        {step === 'done' ? <DoneStep onFinish={finish} /> : null}
        {step !== 'welcome' && step !== 'done' ? <Button kind="quiet" label="Skip this step" onPress={advance} style={styles.skip} /> : null}
      </Screen>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.background },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingLeft: space.xl, paddingRight: space.sm, minHeight: 56 },
  step: { gap: space.xl },
  skip: { alignSelf: 'center' },
});
