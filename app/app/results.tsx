/** Results: words understood per system, learning over versions, live use, the gate's calibrated point, and one footnote. */
import { router, Stack } from 'expo-router';
import type { ReactNode } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import { useServerData } from '@/features/connection/useServerData';
import { LearningChart } from '@/features/teach/LearningChart';
import { percent, shortVersion } from '@/features/teach/ModelCard';
import { resultsSchema, type HeadlineRow, type Results } from '@/features/teach/teachApi';
import { colors, radius, space } from '@/theme';

/** The rows the screen always shows, in reading order, with a dash where nothing is measured yet. */
function headlineRows(results: Results): HeadlineRow[] {
  // The server names rows for the evaluation write-up ("His model v2"); on his phone it is his own.
  const rows = results.headline.map((r) => ({ ...r, system: r.system.replace(/^His model/, 'Your model') }));
  if (!rows.some((r) => r.kind === 'listener' && r.system === 'New listeners')) rows.unshift({ system: 'New listeners', kind: 'listener', quiet: null, babble_5db: null });
  if (!rows.some((r) => r.kind === 'stock')) rows.push({ system: 'Stock Whisper', kind: 'stock', quiet: null, babble_5db: null });
  if (!rows.some((r) => r.kind === 'model')) rows.push({ system: 'Your model', kind: 'model', quiet: null, babble_5db: null });
  return rows;
}

/** A section with a heading and one white card. */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={styles.section}>
      <AppText variant="heading" accessibilityRole="header">
        {title}
      </AppText>
      <View style={styles.card}>{children}</View>
    </View>
  );
}

function Cell({ value }: { value: { words_understood: number; n: number } | null | undefined }) {
  return (
    <View style={styles.num}>
      <AppText variant="label" style={styles.figure}>
        {percent(value?.words_understood)}
      </AppText>
      <AppText variant="caption" tone="muted" style={styles.figure}>
        {value ? `n ${value.n}` : 'n 0'}
      </AppText>
    </View>
  );
}

function Headline({ results }: { results: Results }) {
  const rows = headlineRows(results);
  return (
    <Section title="Words understood">
      <View accessibilityRole="summary">
        <View style={[styles.tr, styles.th]}>
          <AppText variant="caption" tone="muted" style={styles.sys}>
            System
          </AppText>
          <AppText variant="caption" tone="muted" style={[styles.num, styles.figure]}>
            Quiet
          </AppText>
          <AppText variant="caption" tone="muted" style={[styles.num, styles.figure]} accessibilityLabel="Babble at 5 decibels">
            Babble
          </AppText>
        </View>
        {rows.map((row, index) => {
          const active = row.system.endsWith('(active)');
          return (
            <View
              key={row.system}
              style={[styles.tr, active && styles.activeRow, index === rows.length - 1 && styles.lastRow]}
              accessible
              accessibilityLabel={`${row.system}: quiet ${percent(row.quiet?.words_understood)}, babble ${percent(row.babble_5db?.words_understood)}`}>
              <AppText variant={active ? 'label' : 'body'} style={styles.sys}>
                {row.system}
              </AppText>
              <Cell value={row.quiet} />
              <Cell value={row.babble_5db} />
            </View>
          );
        })}
      </View>
    </Section>
  );
}

/** A labelled figure in the live-use grid. */
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat} accessible accessibilityLabel={`${label}: ${value}`}>
      <AppText variant="heading" style={styles.figureLeft}>
        {value}
      </AppText>
      <AppText variant="caption" tone="muted">
        {label}
      </AppText>
    </View>
  );
}

/** Milliseconds as seconds with one decimal, or a dash. */
function seconds(ms: number | null): string {
  return ms === null ? '–' : `${(ms / 1000).toFixed(1)} s`;
}

/** A 0 to 1 rate as a percentage, or a dash. */
function rate(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : `${Math.round(value * 1000) / 10}%`;
}

function LiveUse({ live }: { live: Results['live'] }) {
  if (live.turns === 0) {
    return (
      <Section title="Live use">
        <AppText tone="muted">No conversations yet. Speed and safety appear after you use Talk.</AppText>
      </Section>
    );
  }
  return (
    <Section title="Live use">
      <View style={styles.grid}>
        <Stat label="Median time to text" value={seconds(live.ms_end_to_text.median)} />
        <Stat label="Median time to voice" value={seconds(live.ms_end_to_audio.median)} />
        <Stat label="Asked you to choose" value={rate(live.ask_rate)} />
        <Stat label="Spoke a wrong sentence" value={rate(live.wrong_spoken_rate)} />
      </View>
      <AppText variant="caption" tone="muted">
        From {live.turns} turns
      </AppText>
    </Section>
  );
}

const providerNames: Record<string, string> = { jev: 'Jev', openai: 'OpenAI' };

function Calibration({ calibration }: { calibration: Results['calibration'] }) {
  const providers = Object.entries(calibration);
  return (
    <Section title="When it speaks without asking">
      {providers.length === 0 ? <AppText tone="muted">Not calibrated yet.</AppText> : null}
      {providers.map(([name, entry]) => {
        const point = entry.curve?.find((p) => p.threshold === entry.speak_threshold);
        return (
          <View key={name} style={styles.provider}>
            <AppText variant="label">
              {providerNames[name] ?? name} · speaks above {entry.speak_threshold?.toFixed(2) ?? '–'}
            </AppText>
            <AppText variant="caption" tone="muted">
              Wrong but spoken {rate(point?.wrong_spoken_rate)} · asks {rate(point?.ask_rate)} · n {entry.n ?? 0}
            </AppText>
          </View>
        );
      })}
    </Section>
  );
}

export default function ResultsScreen() {
  const { data, error, loading, reload } = useServerData<unknown>('/results');
  const parsed = data ? resultsSchema.safeParse(data) : null;
  const results = parsed?.success ? parsed.data : null;
  const points = (results?.learning ?? []).map((row) => ({ label: shortVersion(row.version), quiet: row.quiet?.words_understood ?? null, babble: row.babble_5db?.words_understood ?? null }));

  return (
    <Screen>
      <Stack.Screen options={{ title: 'Results' }} />
      {loading && !data ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={reload} /> : null}
      {parsed && !parsed.success ? <ErrorNote message="The results from the server were not readable." onRetry={reload} /> : null}
      {results && results.test_set.clips === 0 ? (
        <View style={styles.card}>
          <AppText variant="label">No test sentences yet — record them in Teach.</AppText>
          <Button kind="primary" label="Record test sentences" onPress={() => router.push({ pathname: '/onboarding', params: { step: 'test' } })} />
        </View>
      ) : null}
      {results ? (
        <>
          <Headline results={results} />
          <Section title="Learning over time">{points.length ? <LearningChart points={points} /> : <AppText tone="muted">No trained versions yet.</AppText>}</Section>
          <LiveUse live={results.live} />
          <Calibration calibration={results.calibration} />
          <AppText variant="caption" tone="muted">
            {results.test_set.clips} test clips. {results.footnote}
          </AppText>
        </>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.md },
  card: { gap: space.md, padding: space.xl, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
  tr: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  th: { paddingTop: 0 },
  activeRow: { borderBottomColor: colors.text },
  lastRow: { borderBottomWidth: 0, paddingBottom: 0 },
  sys: { flex: 1 },
  num: { width: 76, alignItems: 'flex-end' },
  figure: { textAlign: 'right', fontVariant: ['tabular-nums'] },
  figureLeft: { fontVariant: ['tabular-nums'] },
  grid: { flexDirection: 'row', flexWrap: 'wrap', rowGap: space.lg },
  stat: { width: '50%', gap: 2, paddingRight: space.md },
  provider: { gap: 2 },
});
