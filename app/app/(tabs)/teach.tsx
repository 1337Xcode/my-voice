/** Teach: his model and training data (spec 11.5). Recording arrives in phase 2. */
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import { useServerData } from '@/features/connection/useServerData';
import { colors, radius, space } from '@/theme';

type State = { model_version: string; clips: { total: number; train: number; test: number }; review_count: number };

export default function TeachScreen() {
  const { data, error, loading, reload } = useServerData<State>('/state');
  return (
    <Screen>
      {loading && !data ? <ActivityIndicator color={colors.muted} /> : null}
      {error ? <ErrorNote message={error} onRetry={reload} /> : null}
      {data ? (
        <View style={styles.card} accessible accessibilityLabel={`Your model: ${data.model_version}. ${data.clips.train} training clips, ${data.clips.test} test clips.`}>
          <AppText variant="caption" tone="muted">
            Your model
          </AppText>
          <AppText variant="title">{data.model_version === 'stock' ? 'Not trained yet' : data.model_version}</AppText>
          <AppText tone="muted">
            {data.clips.train} training clips · {data.clips.test} test clips
          </AppText>
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.sm, padding: space.xl, backgroundColor: colors.surface, borderRadius: radius, borderWidth: 1, borderColor: colors.border },
});
