// Adds the home-screen widgets and the cleartext network config to the Android project `one prebuild` generates.
// One's prebuild has no Android widget support, so this runs after it; it is safe to run twice.
import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// One's prebuild skips folders named android; anywhere else it would compile this Kotlin a second time.
const source = path.join(root, 'targets', 'android')
const main = path.join(root, 'android', 'app', 'src', 'main')
const manifestPath = path.join(main, 'AndroidManifest.xml')
const gradlePath = path.join(root, 'android', 'app', 'build.gradle')

if (!existsSync(manifestPath)) throw new Error('Run `one prebuild --platform android` first: no AndroidManifest.xml')
if (!readFileSync(gradlePath, 'utf8').includes('namespace "dev.mako.capacity"')) {
  throw new Error('The widget imports dev.mako.capacity.R, but android/app/build.gradle has another namespace')
}

const javaDir = path.join(main, 'java', 'dev', 'mako', 'capacity', 'widget')
mkdirSync(javaDir, { recursive: true })
for (const file of ['CapacityWidget.kt', 'AgentsWidget.kt']) copyFileSync(path.join(source, 'java', file), path.join(javaDir, file))
cpSync(path.join(source, 'res'), path.join(main, 'res'), { recursive: true })

const drawables = path.join(main, 'res', 'drawable-nodpi')
mkdirSync(drawables, { recursive: true })
for (const provider of ['claude', 'codex']) {
  copyFileSync(path.join(root, 'assets', 'providers', `${provider}.png`), path.join(drawables, `provider_${provider}.png`))
}

// Colours come from theme.json, the one palette the app and both widgets share.
const theme = JSON.parse(readFileSync(path.join(root, 'theme.json'), 'utf8'))
const colours = {
  capacity_background: theme.background,
  capacity_text: theme.text,
  capacity_secondary: theme.secondary,
  capacity_track: theme.track,
  capacity_signal_green: theme.signal.green,
  capacity_signal_yellow: theme.signal.yellow,
  capacity_signal_orange: theme.signal.orange,
  capacity_signal_red: theme.signal.red,
}
const colourXml = Object.entries(colours)
  .map(([name, value]) => `  <color name="${name}">${value}</color>`)
  .join('\n')
writeFileSync(path.join(main, 'res', 'values', 'capacity_colors.xml'), `<?xml version="1.0" encoding="utf-8"?>\n<resources>\n${colourXml}\n</resources>\n`)

let manifest = readFileSync(manifestPath, 'utf8')
if (!manifest.includes('android:networkSecurityConfig')) {
  manifest = manifest.replace('<application', '<application\n      android:networkSecurityConfig="@xml/network_security_config"')
}
const receiver = (name, info) => `
    <receiver android:name=".widget.${name}" android:exported="false">
      <intent-filter>
        <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
      </intent-filter>
      <meta-data android:name="android.appwidget.provider" android:resource="@xml/${info}" />
    </receiver>`
const receivers = [
  ['CapacitySmallWidget', 'capacity_widget_small'],
  ['CapacityMediumWidget', 'capacity_widget_medium'],
  ['AgentsWidget', 'agents_widget'],
]
  .filter(([name]) => !manifest.includes(`.widget.${name}"`))
  .map(([name, info]) => receiver(name, info))
  .join('')
if (receivers) {
  const closing = manifest.lastIndexOf('</application>')
  if (closing < 0) throw new Error('AndroidManifest.xml has no </application>')
  manifest = `${manifest.slice(0, closing)}${receivers.trimStart()}\n    ${manifest.slice(closing)}`
}
writeFileSync(manifestPath, manifest)
console.log('Capacity widgets and network security config added to the Android project')
