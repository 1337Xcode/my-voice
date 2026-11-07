/** The sentence in very large type facing the listener: never scrolls; long speech is paged; Flip turns it 180°. */
import { ChevronLeft, ChevronRight, RefreshCcw } from 'lucide-react-native';
import { MotiView } from 'moti';
import { ReactNode, useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { stateTransition, useReduceMotion } from '@/features/motion/useReduceMotion';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, pill, space, target, textScales } from '@/theme';

// About this many characters fit on one page at the "Large" size without scrolling.
const PAGE_CHARS = 110;

/** Splits text at sentence ends into pages of at most `limit` characters (a very long sentence gets its own page). */
export function pagesOf(text: string, limit: number): string[] {
  const sentences = text.match(/[^.!?]+[.!?]*\s*/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];
  const pages: string[] = [];
  for (const sentence of sentences) {
    const last = pages[pages.length - 1];
    if (last && last.length + sentence.length + 1 <= limit) pages[pages.length - 1] = `${last} ${sentence}`;
    else pages.push(sentence);
  }
  return pages.length ? pages : [text];
}

/** 46 pt for short sentences, stepping down to 34 pt (the floor) for long ones, before his text size. */
function sentenceSize(page: string): number {
  if (page.length <= 40) return 46;
  if (page.length <= 75) return 40;
  return 34;
}

type Props = { text: string; status: ReactNode };

export function SentenceCard({ text, status }: Props) {
  const reduce = useReduceMotion();
  const { settings } = useSettings();
  const pages = useMemo(() => pagesOf(text, Math.round(PAGE_CHARS / textScales[settings.textSize])), [text, settings.textSize]);
  const [page, setPage] = useState(0);
  const [flipped, setFlipped] = useState(false);
  useEffect(() => setPage(0), [text]);
  const current = pages[Math.min(page, pages.length - 1)];

  return (
    <MotiView from={{ opacity: 0, translateY: reduce ? 0 : 12 }} animate={{ opacity: 1, translateY: 0 }} transition={stateTransition(reduce)} style={styles.card}>
      <View style={styles.top}>
        <View style={styles.status}>{status}</View>
        <Pressable accessibilityRole="button" accessibilityLabel={flipped ? 'Turn the sentence back' : 'Flip the sentence for the person opposite'} onPress={() => setFlipped((f) => !f)} hitSlop={8} style={styles.flip}>
          <RefreshCcw size={18} color={colors.text} />
          <AppText variant="caption">Flip</AppText>
        </Pressable>
      </View>
      <MotiView animate={{ rotate: flipped ? '180deg' : '0deg' }} transition={stateTransition(reduce)} style={styles.body}>
        <AppText variant="sentence" size={sentenceSize(current)} accessibilityRole="header" accessibilityLiveRegion="assertive" testID="spoken-sentence">
          {current}
        </AppText>
      </MotiView>
      {pages.length > 1 ? (
        <View style={styles.pager}>
          <Pressable accessibilityRole="button" accessibilityLabel="Previous sentence" disabled={page === 0} onPress={() => setPage((p) => p - 1)} style={[styles.pageButton, page === 0 && styles.hidden]}>
            <ChevronLeft size={22} color={colors.text} />
          </Pressable>
          <AppText variant="caption" tone="muted">
            Sentence {page + 1} of {pages.length}
          </AppText>
          <Pressable accessibilityRole="button" accessibilityLabel="Next sentence" disabled={page === pages.length - 1} onPress={() => setPage((p) => p + 1)} style={[styles.pageButton, page === pages.length - 1 && styles.hidden]}>
            <ChevronRight size={22} color={colors.text} />
          </Pressable>
        </View>
      ) : null}
    </MotiView>
  );
}

const styles = StyleSheet.create({
  card: { flexGrow: 1, flexShrink: 1, minHeight: 220, backgroundColor: colors.surface, borderRadius: 28, borderWidth: 1, borderColor: colors.border, padding: space.xl, gap: space.lg },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.md },
  status: { flex: 1 },
  flip: { flexDirection: 'row', alignItems: 'center', gap: space.xs, minHeight: target.min - 8, paddingHorizontal: space.md, borderRadius: pill, backgroundColor: colors.tint },
  body: { flex: 1, justifyContent: 'center' },
  pager: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  pageButton: { width: target.min, height: target.min, borderRadius: target.min / 2, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tint },
  hidden: { opacity: 0 },
});
