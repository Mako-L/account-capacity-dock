import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import { one } from 'one/vite'
import palette from './theme.json' with { type: 'json' }

const APP_GROUP = 'group.dev.mako.capacity'

const iconData = (name: string) =>
  readFileSync(new URL(`./assets/providers/${name}-64.png`, import.meta.url)).toString('base64')

// one prebuild generates a WidgetUI renderer; we replace it with our own SwiftUI widget.
const widgetSource = () =>
  readFileSync(new URL('./targets/widget/CapacityWidget.swift', import.meta.url), 'utf8')
    .replace('__APP_GROUP__', APP_GROUP)
    .replace('__CLAUDE_PNG__', iconData('claude'))
    .replace('__CODEX_PNG__', iconData('codex'))

export default defineConfig({
  plugins: [
    one({
      web: {
        defaultRenderMode: 'spa',
      },

      native: {
        app: {
          name: 'MakoCapacity',
          displayName: 'Capacity',
          userInterfaceStyle: 'dark',
          icon: {
            source: './public/app-icon.png',
            backgroundColor: palette.background,
          },
          splash: {
            source: './public/splash.png',
            backgroundColor: palette.background,
            width: 200,
          },
          ios: {
            bundleId: 'dev.mako.capacity',
            deploymentTarget: '17.0',
            widgets: {
              appGroup: APP_GROUP,
              kind: 'MakoCapacity',
              displayName: 'Capacity',
              description: 'The most constrained accounts and how much of each quota is used.',
              families: ['systemSmall', 'systemMedium'],
            },
          },
          android: { applicationId: 'dev.mako.capacity' },
          patches: [
            { platform: 'ios', file: 'OneWidgets/OneWidget.swift', patch: () => widgetSource() },
          ],
        },
      },
    }),
  ],
})
