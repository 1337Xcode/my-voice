/** The bottom tab bar: a tinted track of pills, the selected one near-black with white text and icon. */
import type { BottomTabBarProps } from 'expo-router/tabs';
import { AudioLines, GraduationCap, MessageSquareText, Phone, type LucideIcon } from 'lucide-react-native';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, pill, space, target } from '@/theme';

const icons: Record<string, LucideIcon> = { index: AudioLines, phrases: MessageSquareText, teach: GraduationCap, calls: Phone };

export function PillTabBar({ state, descriptors, emitter, navigateToTab, insets }: BottomTabBarProps) {
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, space.md) }]}>
      <View style={styles.track} accessibilityRole="tablist">
        {state.routes.map((route, index) => {
          const focused = index === state.index;
          const title = descriptors[route.key]?.options.title ?? route.name;
          const Icon = icons[route.name] ?? AudioLines;
          const onPress = () => {
            const event = emitter.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
            if (!focused && !event.defaultPrevented) navigateToTab(route.key);
          };
          return (
            <Pressable
              key={route.key}
              accessibilityRole="tab"
              accessibilityLabel={title}
              accessibilityState={{ selected: focused }}
              onPress={onPress}
              style={({ pressed }) => [styles.tab, focused && styles.selected, pressed && !focused && styles.pressed]}>
              <Icon size={20} color={focused ? colors.inkText : colors.text} strokeWidth={2} />
              <AppText variant="caption" tone={focused ? 'inverse' : 'default'} numberOfLines={1} maxFontSizeMultiplier={1.3} unscaled>
                {title}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { paddingHorizontal: space.lg, paddingTop: space.sm, backgroundColor: colors.background },
  track: { flexDirection: 'row', padding: space.xs, gap: space.xs, borderRadius: pill, backgroundColor: colors.tint },
  tab: { flex: 1, minHeight: target.min + 8, borderRadius: pill, alignItems: 'center', justifyContent: 'center', gap: 2 },
  selected: { backgroundColor: colors.ink },
  pressed: { opacity: 0.7 },
});
