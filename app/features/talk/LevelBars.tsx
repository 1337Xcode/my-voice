/** The live input meter: one bar per 100 ms of room sound, newest on the right, so he can see he is being heard. */
import { StyleSheet, View } from 'react-native';

import { colors } from '@/theme';

const BAR_COUNT = 30;
const MAX_HEIGHT = 64;
const MIN_HEIGHT = 4;

export function LevelBars({ levels, frozen = false }: { levels: number[]; frozen?: boolean }) {
  const padded = [...Array(Math.max(0, BAR_COUNT - levels.length)).fill(0), ...levels.slice(-BAR_COUNT)] as number[];
  return (
    <View style={styles.row} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {padded.map((level, index) => (
        <View
          key={index}
          style={[styles.bar, { height: MIN_HEIGHT + level * (MAX_HEIGHT - MIN_HEIGHT), backgroundColor: frozen ? colors.faint : colors.accent }]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { height: MAX_HEIGHT, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 },
  bar: { width: 5, borderRadius: 3 },
});
