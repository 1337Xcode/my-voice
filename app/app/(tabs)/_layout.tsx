/** The four tabs: Talk, Phrases, Teach, Calls (spec 11.2). Settings opens from the gear on Talk. */
import { Link, Tabs } from 'expo-router';
import { SymbolView, SymbolViewProps } from 'expo-symbols';
import { ColorValue, Pressable, StyleSheet } from 'react-native';

import { colors, fonts, target } from '@/theme';

type SymbolName = SymbolViewProps['name'];

/** A tab icon from SF Symbols on iOS and Material Symbols elsewhere. */
function tabIcon(ios: string, other: string) {
  const name = { ios, android: other, web: other } as SymbolName;
  return ({ color }: { color: ColorValue }) => <SymbolView name={name} tintColor={color} size={26} />;
}

function SettingsButton() {
  return (
    <Link href="/settings" asChild>
      <Pressable accessibilityRole="button" accessibilityLabel="Settings" hitSlop={8} style={styles.gear}>
        <SymbolView name={{ ios: 'gearshape', android: 'settings', web: 'settings' } as SymbolName} tintColor={colors.text} size={26} />
      </Pressable>
    </Link>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontFamily: fonts.medium, fontSize: 13 },
        tabBarStyle: { backgroundColor: colors.background, borderTopColor: colors.border },
        headerStyle: { backgroundColor: colors.background },
        headerTitleStyle: { fontFamily: fonts.semibold, fontSize: 20 },
        headerShadowVisible: false,
      }}>
      <Tabs.Screen name="index" options={{ title: 'Talk', tabBarIcon: tabIcon('waveform', 'graphic_eq'), headerRight: SettingsButton }} />
      <Tabs.Screen name="phrases" options={{ title: 'Phrases', tabBarIcon: tabIcon('text.bubble', 'chat') }} />
      <Tabs.Screen name="teach" options={{ title: 'Teach', tabBarIcon: tabIcon('graduationcap', 'school') }} />
      <Tabs.Screen name="calls" options={{ title: 'Calls', tabBarIcon: tabIcon('phone', 'call') }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  gear: { minWidth: target.min, minHeight: target.min, alignItems: 'center', justifyContent: 'center', marginRight: 4 },
});
