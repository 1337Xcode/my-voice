/** The four tabs: Talk, Phrases, Teach, Calls (spec 11.2), on a pill tab bar. Settings opens from the gear on Talk. */
import { Tabs } from 'expo-router';

import { PillTabBar } from '@/features/navigation/PillTabBar';
import { colors, fonts } from '@/theme';

export default function TabLayout() {
  return (
    <Tabs
      tabBar={(props) => <PillTabBar {...props} />}
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTitleStyle: { fontFamily: fonts.semibold, fontSize: 22, color: colors.text },
        headerTitleAlign: 'left',
        headerTitleContainerStyle: { paddingLeft: 8 },
        headerShadowVisible: false,
        sceneStyle: { backgroundColor: colors.background },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Talk', headerShown: false }} />
      <Tabs.Screen name="phrases" options={{ title: 'Phrases' }} />
      <Tabs.Screen name="teach" options={{ title: 'Teach' }} />
      <Tabs.Screen name="calls" options={{ title: 'Calls' }} />
    </Tabs>
  );
}
