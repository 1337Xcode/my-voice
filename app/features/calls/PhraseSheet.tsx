/** During a call: his phrases in a sheet; one tap says it into the call. */
import { Volume2 } from 'lucide-react-native';
import { FlatList, Modal, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { usePhrases, type Phrase } from '@/features/phrases/PhrasesProvider';
import { colors, maxContentWidth, radius, space, target } from '@/theme';

type Props = { visible: boolean; onClose: () => void; onSay: (phrase: Phrase) => void };

export function PhraseSheet({ visible, onClose, onSay }: Props) {
  const { mostUsed, phrases } = usePhrases();
  const ordered = [...mostUsed(6), ...phrases.filter((p) => !mostUsed(6).includes(p))];
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" accessibilityRole="button" />
        <View style={styles.sheet} accessibilityViewIsModal>
          <View style={styles.head}>
            <AppText variant="heading" accessibilityRole="header">
              Phrases
            </AppText>
            <Button label="Close" kind="quiet" onPress={onClose} />
          </View>
          <FlatList
            data={ordered}
            keyExtractor={(p) => p.id}
            contentContainerStyle={styles.list}
            renderItem={({ item }) => (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={item.text}
                onPress={() => {
                  onSay(item);
                  onClose();
                }}
                style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
                <View style={styles.icon}>
                  <Volume2 size={18} color={colors.text} />
                </View>
                <AppText variant="label" style={styles.flex}>
                  {item.text}
                </AppText>
              </Pressable>
            )}
          />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  backdrop: { flex: 1, justifyContent: 'flex-end', alignItems: 'center', backgroundColor: 'rgba(30,26,24,0.35)' },
  sheet: { width: '100%', maxWidth: maxContentWidth, maxHeight: '75%', paddingTop: space.lg, backgroundColor: colors.background, borderTopLeftRadius: 28, borderTopRightRadius: 28 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: space.xl },
  list: { padding: space.xl, gap: space.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: target.min + 12, paddingHorizontal: space.lg, paddingVertical: space.sm, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pressed: { backgroundColor: colors.tint },
  icon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tint },
});
