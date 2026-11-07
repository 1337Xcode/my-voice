/** A scrollable screen body with the app's background and padding. */
import { ReactNode } from 'react';
import { ScrollView, StyleSheet, View, ViewStyle } from 'react-native';

import { colors, space } from '@/theme';

type Props = { children: ReactNode; scroll?: boolean; style?: ViewStyle };

export function Screen({ children, scroll = true, style }: Props) {
  if (!scroll) return <View style={[styles.fill, styles.pad, style]}>{children}</View>;
  return (
    <ScrollView style={styles.fill} contentContainerStyle={[styles.pad, style]} keyboardShouldPersistTaps="handled">
      {children}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.background },
  pad: { padding: space.lg, gap: space.lg },
});
