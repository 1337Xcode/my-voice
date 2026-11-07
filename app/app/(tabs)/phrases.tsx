/** Phrases: his bank by category (spec 11.4). One-tap speaking arrives with the voice in phase 1. */
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import { useServerData } from '@/features/connection/useServerData';
import { colors, radius, space, target } from '@/theme';

type Phrase = { id: string; text: string; category: string; order: number };

/** Groups phrases by category, keeping the bank's order inside each. */
function byCategory(phrases: Phrase[]): [string, Phrase[]][] {
  const groups = new Map<string, Phrase[]>();
  for (const phrase of phrases) groups.set(phrase.category, [...(groups.get(phrase.category) ?? []), phrase]);
  return [...groups.entries()];
}

export default function PhrasesScreen() {
  const { data, error, loading, reload } = useServerData<{ phrases: Phrase[] }>('/phrases');
  return (
    <Screen>
      {loading && !data ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={reload} /> : null}
      {data
        ? byCategory(data.phrases).map(([category, phrases]) => (
            <View key={category} style={styles.group}>
              <AppText variant="heading" accessibilityRole="header">
                {category}
              </AppText>
              {phrases.map((phrase) => (
                <View key={phrase.id} style={styles.phrase}>
                  <AppText variant="label">{phrase.text}</AppText>
                </View>
              ))}
            </View>
          ))
        : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.sm },
  phrase: { minHeight: target.min + 8, justifyContent: 'center', paddingHorizontal: space.lg, paddingVertical: space.md, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
});
