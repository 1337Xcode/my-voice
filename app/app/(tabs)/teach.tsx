/** Teach: his model and Improve now, the next sentence to record, Review, and a link to Results. */
import { router, useFocusEffect } from 'expo-router';
import { ChevronRight } from 'lucide-react-native';
import { useCallback, useRef } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import { useServerData } from '@/features/connection/useServerData';
import { useOnboardingProgress } from '@/features/onboarding/onboardingProgress';
import { ModelCard } from '@/features/teach/ModelCard';
import { RecordCard } from '@/features/teach/RecordCard';
import { ReviewList } from '@/features/teach/ReviewList';
import { resultsSchema, stateSchema } from '@/features/teach/teachApi';
import { colors, radius, space, target } from '@/theme';

/** A full-width row that opens another screen. */
function LinkRow({ title, detail, onPress }: { title: string; detail?: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="link" accessibilityLabel={detail ? `${title}. ${detail}` : title} onPress={onPress} style={({ pressed }) => [styles.link, pressed && styles.pressed]}>
      <View style={styles.flex}>
        <AppText variant="label">{title}</AppText>
        {detail ? (
          <AppText variant="caption" tone="muted">
            {detail}
          </AppText>
        ) : null}
      </View>
      <ChevronRight size={22} color={colors.muted} />
    </Pressable>
  );
}

export default function TeachScreen() {
  const state = useServerData<unknown>('/state');
  const results = useServerData<unknown>('/results');
  const { progress, save } = useOnboardingProgress();
  const parsedState = state.data ? stateSchema.safeParse(state.data) : null;
  const parsedResults = results.data ? resultsSchema.safeParse(results.data) : null;
  const { reload: reloadState } = state;
  const { reload: reloadResults } = results;
  const refresh = useCallback(() => {
    reloadState();
    reloadResults();
  }, [reloadState, reloadResults]);

  // Numbers change after recording elsewhere (onboarding, Results); reload when he comes back, not on first open.
  const seenFocus = useRef(false);
  useFocusEffect(
    useCallback(() => {
      if (seenFocus.current) refresh();
      seenFocus.current = true;
    }, [refresh]),
  );

  const resumeSetup = () => {
    save({ seen: true });
    router.push('/onboarding');
  };

  return (
    <Screen>
      {progress && !progress.finished ? <LinkRow title="Finish setting up" detail="Pick up where you left off" onPress={resumeSetup} /> : null}
      {state.loading && !parsedState ? <ActivityIndicator color={colors.muted} /> : null}
      {state.error ? <ErrorNote message={state.error} onRetry={refresh} /> : null}
      {parsedState && !parsedState.success ? <ErrorNote message="The model details from the server were not readable." onRetry={refresh} /> : null}
      {parsedState?.success ? <ModelCard state={parsedState.data} results={parsedResults?.success ? parsedResults.data : null} onModelUpdate={refresh} /> : null}
      <RecordCard />
      <ReviewList />
      <LinkRow title="Results" detail="How well it understands you" onPress={() => router.push('/results')} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  link: { flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: target.round, paddingHorizontal: space.xl, paddingVertical: space.md, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
  flex: { flex: 1 },
  pressed: { opacity: 0.75 },
});
