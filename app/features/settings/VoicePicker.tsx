/** Settings › Voice (spec 11.7): the server's voices, each with a sample to hear, one selected. */
import { Check, Play } from 'lucide-react-native';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { z } from 'zod';

import { AppText } from '@/components/AppText';
import { ErrorNote } from '@/components/ErrorNote';
import { mp3Uri, playUri } from '@/features/audio/playback';
import { api } from '@/features/connection/api';
import { useConnection } from '@/features/connection/ConnectionProvider';
import { useServerData } from '@/features/connection/useServerData';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, radius, space, target } from '@/theme';

const voicesSchema = z.object({
  default: z.string().nullable().optional(),
  voices: z.array(z.object({ id: z.string(), name: z.string(), description: z.string().nullable().optional() })),
});
const sampleSchema = z.object({ format: z.string(), data: z.string() });

export function VoicePicker() {
  const { settings, update } = useSettings();
  const { ready } = useConnection();
  const { data, error, loading, reload } = useServerData<unknown>('/voices');
  const [sampling, setSampling] = useState<string | null>(null);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const parsed = data ? voicesSchema.safeParse(data) : null;
  const voices = parsed?.success ? parsed.data : null;
  const selected = settings.voiceId ?? ready?.voice_id ?? voices?.default ?? null;

  const playSample = async (voiceId: string) => {
    setSampling(voiceId);
    setSampleError(null);
    try {
      const sample = sampleSchema.parse(await api<unknown>(settings, `/voices/${encodeURIComponent(voiceId)}/sample?speaker=${settings.dev.speaker}`));
      await playUri(await mp3Uri(sample.data));
    } catch (e) {
      setSampleError(e instanceof z.ZodError ? 'The voice sample was not readable.' : (e as Error).message);
    } finally {
      setSampling(null);
    }
  };

  return (
    <View style={styles.group}>
      <AppText variant="label">Voice</AppText>
      {loading && !voices ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={reload} /> : null}
      {parsed && !parsed.success ? <ErrorNote message="The voice list from the server was not readable." onRetry={reload} /> : null}
      {sampleError ? <ErrorNote message={sampleError} /> : null}
      {voices?.voices.map((voice) => {
        const active = voice.id === selected;
        return (
          <View key={voice.id} style={[styles.row, active && styles.active]}>
            <Pressable accessibilityRole="radio" accessibilityState={{ selected: active }} accessibilityLabel={voice.name} onPress={() => update({ voiceId: voice.id })} style={styles.choose}>
              <View style={[styles.check, active && styles.checkOn]}>{active ? <Check size={16} color={colors.inkText} strokeWidth={2.5} /> : null}</View>
              <View style={styles.flex}>
                <AppText variant="label">{voice.name}</AppText>
                {voice.description ? (
                  <AppText variant="caption" tone="muted" numberOfLines={2}>
                    {voice.description}
                  </AppText>
                ) : null}
              </View>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel={`Hear ${voice.name}`} onPress={() => void playSample(voice.id)} disabled={sampling !== null} style={styles.play}>
              {sampling === voice.id ? <ActivityIndicator size="small" color={colors.text} /> : <Play size={18} color={colors.text} fill={colors.text} />}
            </Pressable>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.sm },
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingLeft: space.lg, paddingRight: space.sm, minHeight: target.min + 16, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  active: { borderColor: colors.text },
  choose: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.md },
  check: { width: 24, height: 24, borderRadius: 12, borderWidth: 1.5, borderColor: colors.muted, alignItems: 'center', justifyContent: 'center' },
  checkOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  play: { width: target.min, height: target.min, borderRadius: target.min / 2, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tint },
});
