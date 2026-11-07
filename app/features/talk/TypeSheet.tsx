/** A sheet for typing a sentence to be spoken: one field, Speak and Cancel. */
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, maxContentWidth, radius, space, textScales } from '@/theme';

type Props = { visible: boolean; onClose: () => void; onSpeak: (text: string) => void; online: boolean };

export function TypeSheet({ visible, onClose, onSpeak, online }: Props) {
  const [text, setText] = useState('');
  const { settings } = useSettings();
  useEffect(() => {
    if (visible) setText('');
  }, [visible]);
  const trimmed = text.trim();
  const speak = () => {
    if (!trimmed) return;
    onSpeak(trimmed);
    onClose();
  };
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.backdrop}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" accessibilityRole="button" />
        <View style={styles.sheet} accessibilityViewIsModal>
          <AppText variant="heading" accessibilityRole="header">
            Type it
          </AppText>
          <TextInput
            autoFocus
            multiline
            value={text}
            onChangeText={setText}
            placeholder="What do you want to say?"
            placeholderTextColor={colors.faint}
            accessibilityLabel="Sentence to speak"
            style={[styles.input, { fontSize: 22 * textScales[settings.textSize] }]}
            onSubmitEditing={speak}
            submitBehavior="submit"
          />
          {!online ? (
            <AppText variant="caption" tone="muted">
              Offline: the phone's own voice will say it.
            </AppText>
          ) : null}
          <View style={styles.actions}>
            <Button label="Cancel" kind="quiet" onPress={onClose} />
            <Button label="Speak" kind="primary" onPress={speak} disabled={!trimmed} />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: 'flex-end', alignItems: 'center', backgroundColor: 'rgba(30,26,24,0.35)' },
  sheet: { width: '100%', maxWidth: maxContentWidth, gap: space.lg, padding: space.xl, paddingBottom: space.xxl, backgroundColor: colors.background, borderTopLeftRadius: 28, borderTopRightRadius: 28 },
  input: { minHeight: 120, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, fontFamily: fonts.medium, color: colors.text, textAlignVertical: 'top' },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', gap: space.md },
});
