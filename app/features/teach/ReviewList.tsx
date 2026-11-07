/** Teach › Review: everyday sentences spoken without a check, each approved, rejected or corrected in one tap (spec 9.2). */
import { Check, Pencil, Play, X } from 'lucide-react-native';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { playUri } from '@/features/audio/playback';
import { useServerData } from '@/features/connection/useServerData';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, pill, radius, space, target } from '@/theme';
import { clipAudio, reviewSchema, sendReview, type ReviewItem } from './teachApi';
import { wavUri } from './wav';

// Long lists show in pages so the screen stays light.
const PAGE = 10;

type IconButtonProps = { label: string; icon: typeof Check; onPress: () => void; disabled?: boolean; busy?: boolean };

/** A round 48-point button with a spoken label. */
function IconButton({ label, icon: Icon, onPress, disabled, busy }: IconButtonProps) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} disabled={disabled} style={({ pressed }) => [styles.icon, pressed && styles.pressed, disabled && styles.disabled]}>
      {busy ? <ActivityIndicator size="small" color={colors.text} /> : <Icon size={22} color={colors.text} strokeWidth={2.2} />}
    </Pressable>
  );
}

function ReviewRow({ item, onDone }: { item: ReviewItem; onDone: (turnId: string) => void }) {
  const { settings } = useSettings();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.text);
  const [busy, setBusy] = useState<'play' | 'send' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const play = async () => {
    setBusy('play');
    setError(null);
    try {
      await playUri(await wavUri(new Uint8Array(await clipAudio(settings, item.clip_id))));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const verdict = async (action: 'approve' | 'reject' | 'edit') => {
    if (action === 'edit' && !draft.trim()) return;
    setBusy('send');
    setError(null);
    try {
      await sendReview(settings, item.turn_id, action, action === 'edit' ? draft.trim() : undefined);
      onDone(item.turn_id);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <View style={styles.row}>
      <View style={styles.line}>
        <IconButton label={`Play: ${item.text}`} icon={Play} onPress={() => void play()} busy={busy === 'play'} disabled={busy !== null} />
        {editing ? (
          <TextInput accessibilityLabel="What you said" value={draft} onChangeText={setDraft} autoFocus multiline style={styles.input} onSubmitEditing={() => void verdict('edit')} />
        ) : (
          <AppText variant="label" style={styles.text}>
            {item.text}
          </AppText>
        )}
      </View>
      {editing ? (
        <View style={styles.actions}>
          <Button kind="primary" label="Save" onPress={() => void verdict('edit')} disabled={busy !== null || !draft.trim()} />
          <Button kind="quiet" label="Cancel" onPress={() => setEditing(false)} disabled={busy !== null} />
        </View>
      ) : (
        <View style={styles.actions}>
          <IconButton label={`Right: ${item.text}`} icon={Check} onPress={() => void verdict('approve')} disabled={busy !== null} busy={busy === 'send'} />
          <IconButton label={`Wrong: ${item.text}`} icon={X} onPress={() => void verdict('reject')} disabled={busy !== null} />
          <IconButton label={`Correct the words: ${item.text}`} icon={Pencil} onPress={() => setEditing(true)} disabled={busy !== null} />
        </View>
      )}
      {error ? <ErrorNote message={error} /> : null}
    </View>
  );
}

export function ReviewList() {
  const { data, error, loading, reload } = useServerData<unknown>('/review');
  const [done, setDone] = useState<string[]>([]);
  const [shown, setShown] = useState(PAGE);
  const parsed = data ? reviewSchema.safeParse(data) : null;
  const items = parsed?.success ? parsed.data.items.filter((item) => !done.includes(item.turn_id)) : [];

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <AppText variant="heading">Review</AppText>
        {items.length ? (
          <View style={styles.badge} accessibilityLabel={`${items.length} to check`}>
            <AppText variant="caption" tone="inverse">
              {items.length}
            </AppText>
          </View>
        ) : null}
      </View>
      {loading && !data ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={reload} /> : null}
      {parsed && !parsed.success ? <ErrorNote message="The review list from the server was not readable." onRetry={reload} /> : null}
      {parsed?.success && items.length === 0 ? (
        <AppText tone="muted">Nothing to check right now.</AppText>
      ) : null}
      {items.length ? (
        <View style={styles.list}>
          {items.slice(0, shown).map((item) => (
            <ReviewRow key={item.turn_id} item={item} onDone={(id) => setDone((list) => [...list, id])} />
          ))}
        </View>
      ) : null}
      {items.length > shown ? <Button label={`Show ${Math.min(PAGE, items.length - shown)} more`} onPress={() => setShown((n) => n + PAGE)} style={styles.more} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.md },
  header: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  badge: { minWidth: 28, height: 28, paddingHorizontal: space.sm, borderRadius: pill, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center' },
  list: { backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' },
  row: { gap: space.md, padding: space.lg, borderBottomWidth: 1, borderBottomColor: colors.border },
  line: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  text: { flex: 1 },
  input: { flex: 1, minHeight: target.min, paddingHorizontal: space.md, paddingVertical: space.sm, borderRadius: space.md, borderWidth: 1, borderColor: colors.text, fontFamily: fonts.medium, fontSize: 17, color: colors.text },
  actions: { flexDirection: 'row', gap: space.sm, paddingLeft: target.min + space.md },
  icon: { width: target.min, height: target.min, borderRadius: target.min / 2, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tint },
  pressed: { opacity: 0.75 },
  disabled: { opacity: 0.4 },
  more: { alignSelf: 'flex-start' },
});
