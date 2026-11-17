import { Tabs } from 'one'
import { palette } from '../../components/palette'

// Native tab bars take image icons, not React elements: the two ring shapes, tinted by the tab bar.
const CAPACITY_ICON = { type: 'image', source: require('../../assets/tabs/capacity.png') } as const
const AGENTS_ICON = { type: 'image', source: require('../../assets/tabs/agents.png') } as const

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: palette.background },
        headerTintColor: palette.text,
        tabBarStyle: { backgroundColor: palette.background, borderTopColor: palette.cardBorder },
        tabBarActiveTintColor: palette.text,
        tabBarInactiveTintColor: palette.secondary,
        sceneStyle: { backgroundColor: palette.background },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Capacity', tabBarIcon: CAPACITY_ICON }} />
      <Tabs.Screen name="agents" options={{ title: 'Agents', tabBarIcon: AGENTS_ICON }} />
    </Tabs>
  )
}
