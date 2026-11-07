/** Setup step 3 (spec 10): his phrase bank, where he deletes, edits or adds phrases by typing; saved with `PUT /phrases`. */
import { Plus, Trash2 } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { z } from 'zod';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { api } from '@/features/connection/api';
import { usePhrases } from '@/features/phrases/PhrasesProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { fetchParsed } from '@/features/teach/teachApi';
import { colors, fonts, radius, space, target } from '@/theme';

const bankSchema = z.object({ phrases: z.array(z.object({ id: z.string(), text: z.string(), category: z.string(), order: z.number(), pinned: z.boolean().optional() })) });
type EditablePhrase = z.infer<typeof bankSchema>['phrases'][number];

/** A new phrase id that will not clash with the server's. */
function newPhraseId(): string {
  return `p-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
}

export function PhrasesStep({ onNext }: { onNext: () => void }) {
  const { settings } = useSettings();
  const { reload: reloadPhrases } = usePhrases();
  const [phrases, setPhrases] = useState<EditablePhrase[] | null>(null);
  const [original, setOriginal] = useState('');
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    fetchParsed(settings, '/phrases', bankSchema)
      .then((bank) => {
        setPhrases(bank.phrases);
        setOriginal(JSON.stringify(bank.phrases));
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
    // Loads once per attempt; the settings only supply the address.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const edit = (id: string, text: string) => setPhrases((list) => list?.map((p) => (p.id === id ? { ...p, text } : p)) ?? null);
  const remove = (id: string) => setPhrases((list) => list?.filter((p) => p.id !== id) ?? null);
  const add = () => {
    const text = draft.trim();
    if (!text || !phrases) return;
    setPhrases([...phrases, { id: newPhraseId(), text, category: 'Mine', order: phrases.length, pinned: false }]);
    setDraft('');
  };

  /** Saves only when something changed, so the voice cache is not rebuilt for nothing. */
  const save = async () => {
    if (!phrases) return onNext();
    const cleaned = phrases.filter((p) => p.text.trim()).map((p, order) => ({ ...p, text: p.text.trim(), order }));
    if (JSON.stringify(cleaned) === original) return onNext();
    setSaving(true);
    setError(null);
    try {
      await api(settings, `/phrases?speaker=${settings.dev.speaker}`, { method: 'PUT', body: JSON.stringify(cleaned) });
      reloadPhrases();
      onNext();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.step}>
      <AppText variant="title" accessibilityRole="header">
        Your phrases
      </AppText>
      <AppText tone="muted">Tap a phrase to change its words. You can come back to this later.</AppText>
      {!phrases && !error ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={phrases ? () => void save() : () => setAttempt((n) => n + 1)} /> : null}
      {phrases ? (
        <View style={styles.list}>
          {phrases.map((phrase) => (
            <View key={phrase.id} style={styles.row}>
              <TextInput accessibilityLabel={`Phrase: ${phrase.text}`} value={phrase.text} onChangeText={(text) => edit(phrase.id, text)} style={styles.input} />
              <Pressable accessibilityRole="button" accessibilityLabel={`Delete: ${phrase.text}`} onPress={() => remove(phrase.id)} style={({ pressed }) => [styles.icon, pressed && styles.pressed]}>
                <Trash2 size={20} color={colors.text} />
              </Pressable>
            </View>
          ))}
          <View style={[styles.row, styles.last]}>
            <TextInput accessibilityLabel="New phrase" placeholder="Add a phrase" placeholderTextColor={colors.faint} value={draft} onChangeText={setDraft} onSubmitEditing={add} style={styles.input} />
            <Pressable accessibilityRole="button" accessibilityLabel="Add phrase" onPress={add} disabled={!draft.trim()} style={({ pressed }) => [styles.icon, pressed && styles.pressed, !draft.trim() && styles.disabled]}>
              <Plus size={22} color={colors.text} />
            </Pressable>
          </View>
        </View>
      ) : null}
      <Button kind="primary" label={saving ? 'Saving' : 'Continue'} onPress={() => void save()} disabled={saving || !phrases} />
    </View>
  );
}

const styles = StyleSheet.create({
  step: { gap: space.xl },
  list: { backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingLeft: space.lg, paddingRight: space.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  last: { borderBottomWidth: 0 },
  input: { flex: 1, minHeight: target.min + 8, paddingVertical: space.md, fontFamily: fonts.medium, fontSize: 17, color: colors.text },
  icon: { width: target.min, height: target.min, borderRadius: target.min / 2, alignItems: 'center', justifyContent: 'center' },
  pressed: { backgroundColor: colors.tint },
  disabled: { opacity: 0.4 },
});
