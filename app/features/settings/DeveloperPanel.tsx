/** The hidden developer panel (spec 11.2): server URL, token, active speaker, thresholds, endpoint silence, partials. */
import { useState } from 'react';
import { Pressable, StyleSheet, Switch, TextInput, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Choice } from '@/components/Choice';
import { Speaker, useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, radius, space, target } from '@/theme';

const speakers: { value: Speaker; label: string }[] = [
  { value: 'P1', label: 'P1' },
  { value: 'S1', label: 'S1' },
];

/** A labelled text field that saves when editing ends. */
function Field({ label, value, onSave, secure = false, numeric = false }: { label: string; value: string; onSave: (value: string) => void; secure?: boolean; numeric?: boolean }) {
  const [draft, setDraft] = useState(value);
  return (
    <View style={styles.field}>
      <AppText variant="caption" tone="muted">
        {label}
      </AppText>
      <TextInput
        accessibilityLabel={label}
        value={draft}
        onChangeText={setDraft}
        onEndEditing={() => onSave(draft.trim())}
        onBlur={() => onSave(draft.trim())}
        secureTextEntry={secure}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType={numeric ? 'decimal-pad' : 'default'}
        style={styles.input}
      />
    </View>
  );
}

/** Parses a number field, keeping the old value when the text is not a number in range. */
function parseIn(text: string, fallback: number, min: number, max: number): number {
  const value = Number(text);
  return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
}

export function DeveloperPanel() {
  const { settings, updateDev } = useSettings();
  const dev = settings.dev;
  return (
    <View style={styles.panel}>
      <AppText variant="heading">Developer</AppText>
      <Field label="Server URL" value={dev.serverUrl} onSave={(serverUrl) => updateDev({ serverUrl: serverUrl.replace(/\/$/, '') })} />
      <Field label="App token" value={dev.token} secure onSave={(token) => updateDev({ token })} />
      <Choice label="Active speaker" options={speakers} value={dev.speaker} onChange={(speaker) => updateDev({ speaker, speakerChosen: true })} />
      <Field label="Speak threshold (0.5 to 0.99)" numeric value={String(dev.speakThreshold)} onSave={(t) => updateDev({ speakThreshold: parseIn(t, dev.speakThreshold, 0.5, 0.99) })} />
      <Field label="Pick threshold (0.1 to 0.99)" numeric value={String(dev.pickThreshold)} onSave={(t) => updateDev({ pickThreshold: parseIn(t, dev.pickThreshold, 0.1, 0.99) })} />
      <Field label="End-of-speech silence, ms (500 to 2000)" numeric value={String(dev.endpointSilenceMs)} onSave={(t) => updateDev({ endpointSilenceMs: Math.round(parseIn(t, dev.endpointSilenceMs, 500, 2000)) })} />
      <Pressable style={styles.switchRow} onPress={() => updateDev({ partials: !dev.partials })} accessibilityRole="switch" accessibilityState={{ checked: dev.partials }}>
        <AppText variant="label">Show partial words</AppText>
        <Switch value={dev.partials} onValueChange={(partials) => updateDev({ partials })} trackColor={{ true: colors.accent }} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { gap: space.lg, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  field: { gap: space.xs },
  input: { minHeight: target.min, paddingHorizontal: space.md, borderRadius: radius, borderWidth: 1, borderColor: colors.border, fontFamily: fonts.regular, fontSize: 16, color: colors.text, backgroundColor: colors.background },
  switchRow: { minHeight: target.min, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});
