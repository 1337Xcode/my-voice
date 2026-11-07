/** Settings: Before speaking, Text size, Voice, Microphone. Long-press the version line for the developer panel. */
import { router } from 'expo-router';
import { ChevronRight } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, StyleSheet, Switch, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Choice } from '@/components/Choice';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import { clientVersion } from '@/features/connection/ConnectionProvider';
import { useExperimentAvailability } from '@/features/experiments/ExperimentsSync';
import { DeveloperPanel } from '@/features/settings/DeveloperPanel';
import { MyData } from '@/features/mydata/MyData';
import { MicrophonePicker } from '@/features/settings/MicrophonePicker';
import { ToolkitStatus } from '@/features/toolkit/ToolkitStatus';
import { BeforeSpeaking, useSettings } from '@/features/settings/SettingsProvider';
import { useServerSettingsSync } from '@/features/settings/useServerSettingsSync';
import { VoicePicker } from '@/features/settings/VoicePicker';
import { colors, space, target, TextSize } from '@/theme';

const textSizes: { value: TextSize; label: string }[] = [
  { value: 'large', label: 'Large' },
  { value: 'xl', label: 'Extra large' },
  { value: 'huge', label: 'Huge' },
];

const beforeSpeaking: { value: BeforeSpeaking; label: string }[] = [
  { value: 'speak', label: 'Speak straight away' },
  { value: 'check', label: 'Let me check first' },
];

function SwitchRow({ label, value, onChange }: { label: string; value: boolean; onChange: (value: boolean) => void }) {
  return (
    <Pressable style={styles.switchRow} onPress={() => onChange(!value)} accessibilityRole="switch" accessibilityLabel={label} accessibilityState={{ checked: value }}>
      <AppText variant="label">{label}</AppText>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.ink, false: colors.tint }} thumbColor={colors.surface} />
    </Pressable>
  );
}

export default function SettingsScreen() {
  const { settings, update } = useSettings();
  const sync = useServerSettingsSync();
  const [developer, setDeveloper] = useState(false);
  const experiments = useExperimentAvailability();
  return (
    <Screen>
      {sync.error ? <ErrorNote message={sync.error} onRetry={sync.retry} /> : null}
      <Choice label="Before speaking" options={beforeSpeaking} value={settings.beforeSpeaking} onChange={(value) => update({ beforeSpeaking: value })} />
      <Choice label="Text size" options={textSizes} value={settings.textSize} onChange={(value) => update({ textSize: value })} />
      <View style={styles.switches}>
        <SwitchRow label="High contrast" value={settings.highContrast} onChange={(highContrast) => update({ highContrast })} />
        <SwitchRow label="Reduce motion" value={settings.reduceMotion} onChange={(reduceMotion) => update({ reduceMotion })} />
      </View>
      <VoicePicker />
      <MicrophonePicker />
      <MyData />
      <ToolkitStatus />
      {experiments.realtimeVoice || experiments.lips ? (
        <Pressable style={styles.switchRow} onPress={() => router.push('/experiments')} accessibilityRole="button" accessibilityLabel="Experiments">
          <AppText variant="label">Experiments</AppText>
          <ChevronRight size={20} color={colors.muted} />
        </Pressable>
      ) : null}
      <View style={styles.divider} />
      <Pressable onLongPress={() => setDeveloper((open) => !open)} delayLongPress={800} accessibilityHint="Long-press to open the developer panel">
        <AppText variant="caption" tone="faint">
          Version {clientVersion}
        </AppText>
      </Pressable>
      {developer ? <DeveloperPanel /> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  divider: { height: 1, backgroundColor: colors.border },
  switches: { gap: space.xs },
  switchRow: { minHeight: target.min, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});
