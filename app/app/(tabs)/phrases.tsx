/** Phrases: his bank by category; one tap speaks it, from the stored clip when there is one, offline too. */
import { Volume2 } from 'lucide-react-native';
import { useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ErrorNote } from '@/components/ErrorNote';
import { usePhrases, type Phrase } from '@/features/phrases/PhrasesProvider';
import { colors, pill, radius, space, target } from '@/theme';

const MOST_USED = 'Most used';

function CategoryChips({ categories, selected, onSelect }: { categories: string[]; selected: string; onSelect: (category: string) => void }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} style={styles.chipScroll}>
      {[MOST_USED, ...categories].map((category) => {
        const active = category === selected;
        return (
          <Pressable
            key={category}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => onSelect(category)}
            style={({ pressed }) => [styles.chip, active && styles.chipActive, pressed && !active && styles.pressed]}>
            <AppText variant="label" tone={active ? 'inverse' : 'default'}>
              {category}
            </AppText>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function PhraseRow({ phrase, playing, onPress }: { phrase: Phrase; playing: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={phrase.text}
      accessibilityHint="Speaks this phrase"
      accessibilityState={{ busy: playing }}
      onPress={onPress}
      style={({ pressed }) => [styles.row, phrase.pinned && styles.pinned, (pressed || playing) && styles.rowActive]}>
      <View style={[styles.icon, phrase.pinned && styles.iconPinned, playing && styles.iconPlaying]}>
        <Volume2 size={20} color={playing ? colors.inkText : colors.text} strokeWidth={2} />
      </View>
      <AppText variant="label" style={styles.text}>
        {phrase.text}
      </AppText>
    </Pressable>
  );
}

export default function PhrasesScreen() {
  const { phrases, mostUsed, categories, loading, error, reload, say } = usePhrases();
  const [category, setCategory] = useState(MOST_USED);
  const [playing, setPlaying] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);
  const shown = category === MOST_USED ? mostUsed(12) : phrases.filter((p) => p.pinned || p.category === category);

  const speak = async (phrase: Phrase) => {
    setPlaying(phrase.id);
    setPlayError(null);
    try {
      await say(phrase);
    } catch (e) {
      setPlayError((e as Error).message);
    } finally {
      setTimeout(() => setPlaying((current) => (current === phrase.id ? null : current)), 1_500);
    }
  };

  return (
    <View style={styles.screen}>
      <CategoryChips categories={categories} selected={category} onSelect={setCategory} />
      <FlatList
        data={shown}
        keyExtractor={(phrase) => phrase.id}
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.notes}>
            {error ? <ErrorNote message={error} onRetry={reload} /> : null}
            {playError ? <ErrorNote message={playError} /> : null}
            {loading && phrases.length <= 1 ? <ActivityIndicator color={colors.muted} /> : null}
          </View>
        }
        renderItem={({ item }) => <PhraseRow phrase={item} playing={playing === item.id} onPress={() => void speak(item)} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  chipScroll: { flexGrow: 0, flexShrink: 0 },
  chips: { gap: space.sm, paddingHorizontal: space.xl, paddingTop: space.xs, paddingBottom: space.md, alignItems: 'center' },
  chip: { minHeight: target.min - 4, paddingHorizontal: space.lg, justifyContent: 'center', borderRadius: pill, backgroundColor: colors.tint },
  chipActive: { backgroundColor: colors.ink },
  pressed: { opacity: 0.7 },
  list: { paddingHorizontal: space.xl, paddingBottom: space.xl, gap: space.sm },
  notes: { gap: space.sm, paddingTop: space.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.lg, minHeight: target.min + 20, paddingHorizontal: space.lg, paddingVertical: space.md, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pinned: { backgroundColor: colors.tint, borderColor: colors.tint },
  rowActive: { borderColor: colors.text },
  icon: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tint },
  iconPinned: { backgroundColor: colors.surface },
  iconPlaying: { backgroundColor: colors.ink },
  text: { flex: 1 },
});
