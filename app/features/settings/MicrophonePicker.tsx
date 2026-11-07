/** Settings › Microphone: the inputs the recorder can see, the chosen one marked; system default otherwise. */
import { useAudioDevices } from '@siteed/audio-studio';
import { Check } from 'lucide-react-native';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, radius, space, target } from '@/theme';

function Option({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="radio" accessibilityState={{ selected: active }} accessibilityLabel={label} onPress={onPress} style={[styles.row, active && styles.active]}>
      <View style={[styles.check, active && styles.checkOn]}>{active ? <Check size={16} color={colors.inkText} strokeWidth={2.5} /> : null}</View>
      <AppText variant="label" style={styles.flex} numberOfLines={1}>
        {label}
      </AppText>
    </Pressable>
  );
}

export function MicrophonePicker() {
  const { settings, update } = useSettings();
  const { devices, error } = useAudioDevices();
  const inputs = devices.filter((device) => device.isAvailable && !device.isDefault);
  return (
    <View style={styles.group}>
      <AppText variant="label">Microphone</AppText>
      <Option label="System default" active={!settings.micDeviceId} onPress={() => update({ micDeviceId: null })} />
      {inputs.map((device, index) => (
        <Option key={device.id} label={device.name || `Microphone ${index + 1}`} active={settings.micDeviceId === device.id} onPress={() => update({ micDeviceId: device.id })} />
      ))}
      {error || inputs.length === 0 ? (
        <AppText variant="caption" tone="muted">
          Other microphones appear here once they are connected and allowed.
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.sm },
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.lg, minHeight: target.min + 8, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  active: { borderColor: colors.text },
  check: { width: 24, height: 24, borderRadius: 12, borderWidth: 1.5, borderColor: colors.muted, alignItems: 'center', justifyContent: 'center' },
  checkOn: { backgroundColor: colors.ink, borderColor: colors.ink },
});
