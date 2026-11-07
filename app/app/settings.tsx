/** Settings (spec 11.7). Long-press the version line to open the hidden developer panel. */
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Choice } from '@/components/Choice';
import { Screen } from '@/components/Screen';
import { clientVersion } from '@/features/connection/ConnectionProvider';
import { DeveloperPanel } from '@/features/settings/DeveloperPanel';
import { BeforeSpeaking, useSettings } from '@/features/settings/SettingsProvider';
import { colors, space, TextSize } from '@/theme';

const textSizes: { value: TextSize; label: string }[] = [
  { value: 'large', label: 'Large' },
  { value: 'xl', label: 'Extra large' },
  { value: 'huge', label: 'Huge' },
];

const beforeSpeaking: { value: BeforeSpeaking; label: string }[] = [
  { value: 'speak', label: 'Speak straight away' },
  { value: 'check', label: 'Let me check first' },
];

export default function SettingsScreen() {
  const { settings, update } = useSettings();
  const [developer, setDeveloper] = useState(false);
  return (
    <Screen>
      <Choice label="Before speaking" options={beforeSpeaking} value={settings.beforeSpeaking} onChange={(value) => update({ beforeSpeaking: value })} />
      <Choice label="Text size" options={textSizes} value={settings.textSize} onChange={(value) => update({ textSize: value })} />
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

const styles = StyleSheet.create({ divider: { height: 1, backgroundColor: colors.border, marginVertical: space.sm } });
