/** His most-used phrases as large chips on Talk; one tap speaks one. */
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, radius, space, target } from '@/theme';
import type { Phrase } from './PhrasesProvider';

export function PhraseChips({ phrases, onSay }: { phrases: Phrase[]; onSay: (phrase: Phrase) => void }) {
  return (
    <View style={styles.wrap}>
      {phrases.map((phrase) => (
        <Pressable
          key={phrase.id}
          accessibilityRole="button"
          accessibilityLabel={phrase.text}
          accessibilityHint="Speaks this phrase"
          onPress={() => onSay(phrase)}
          style={({ pressed }) => [styles.chip, phrase.pinned && styles.pinned, pressed && styles.pressed]}>
          <AppText variant="label">{phrase.text}</AppText>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: { maxWidth: '100%', minHeight: target.min + 8, justifyContent: 'center', paddingHorizontal: space.lg, paddingVertical: space.md, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pinned: { backgroundColor: colors.tint, borderColor: colors.tint },
  pressed: { opacity: 0.7 },
});
