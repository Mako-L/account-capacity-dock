import { Slot, Stack, useServerHeadInsertion } from 'one'
import { AppRegistry, Platform } from 'react-native'
import { palette } from '../components/palette'

export default function Layout() {
  useServerHeadInsertion(() => {
    if (Platform.OS !== 'web') {
      return <></>
    }
    AppRegistry.registerComponent('styles', () => () => null)
    // @ts-expect-error web-only api
    return AppRegistry.getApplication('styles', {}).getStyleElement()
  })

  if (Platform.OS === 'web') {
    return (
      <html lang="en-US">
        <head>
          <meta charSet="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5" />
          <title>Capacity</title>
          <link rel="icon" href="/favicon.svg" />
        </head>
        <Slot />
      </html>
    )
  }

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: palette.background },
        headerTintColor: palette.text,
        contentStyle: { backgroundColor: palette.background },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Capacity' }} />
      <Stack.Screen name="account/[id]" options={{ title: 'Account' }} />
      <Stack.Screen name="settings" options={{ title: 'Proxy', presentation: 'modal' }} />
    </Stack>
  )
}
