// Adds the home-screen widgets and the cleartext network config to the Android project `one prebuild` generates.
// One's prebuild has no Android widget support, so this runs after it; it is safe to run twice.
import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
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
for (const file of ['CapacityWidget.kt', 'AgentsWidget.kt', 'WearSync.kt']) copyFileSync(path.join(source, 'java', file), path.join(javaDir, file))
for (const stale of ['layout/capacity_widget.xml', 'layout/capacity_widget_cell.xml', 'xml/capacity_widget_small.xml', 'xml/capacity_widget_medium.xml']) {
  rmSync(path.join(main, 'res', stale), { force: true })
}
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
const colourFile = `<?xml version="1.0" encoding="utf-8"?>\n<resources>\n${colourXml}\n</resources>\n`
writeFileSync(path.join(main, 'res', 'values', 'capacity_colors.xml'), colourFile)

// The Wear OS app: its own module with the phone's application id, fed over the Wearable Data Layer.
const wear = path.join(root, 'android', 'wear')
cpSync(path.join(source, 'wear'), wear, { recursive: true })
const wearRes = path.join(wear, 'src', 'main', 'res')
mkdirSync(path.join(wearRes, 'values'), { recursive: true })
writeFileSync(path.join(wearRes, 'values', 'capacity_colors.xml'), colourFile)
mkdirSync(path.join(wearRes, 'drawable-nodpi'), { recursive: true })
for (const provider of ['claude', 'codex']) {
  copyFileSync(path.join(root, 'assets', 'providers', `${provider}.png`), path.join(wearRes, 'drawable-nodpi', `provider_${provider}.png`))
}
for (const density of ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi']) {
  cpSync(path.join(main, 'res', `mipmap-${density}`), path.join(wearRes, `mipmap-${density}`), { recursive: true })
}
const settingsPath = path.join(root, 'android', 'settings.gradle')
const settings = readFileSync(settingsPath, 'utf8')
if (!settings.includes("include ':wear'")) writeFileSync(settingsPath, settings.replace("include ':app'", "include ':app'\ninclude ':wear'"))
const gradle = readFileSync(gradlePath, 'utf8')
const wearable = 'implementation "com.google.android.gms:play-services-wearable:19.0.0"'
if (!gradle.includes(wearable)) writeFileSync(gradlePath, `${gradle}\ndependencies {\n    ${wearable}\n}\n`)

let manifest = readFileSync(manifestPath, 'utf8')
if (!manifest.includes('android:networkSecurityConfig')) {
  manifest = manifest.replace('<application', '<application\n      android:networkSecurityConfig="@xml/network_security_config"')
}
const receiver = (name, info) => `
    <receiver android:name=".widget.${name}" android:exported="false" android:label="@string/${info}_label">
      <intent-filter>
        <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
      </intent-filter>
      <meta-data android:name="android.appwidget.provider" android:resource="@xml/${info}" />
    </receiver>`
// Earlier builds stamped one-size widgets; drop their receivers so a re-run never points at removed layouts.
manifest = manifest.replace(/\n\s*<receiver android:name="\.widget\.Capacity(Small|Medium)Widget"[\s\S]*?<\/receiver>/g, '')
const service = `
    <service android:name=".widget.AccountsListService" android:exported="false" android:permission="android.permission.BIND_REMOTEVIEWS" />`
if (!manifest.includes('.widget.AccountsListService"')) {
  const closing = manifest.lastIndexOf('</application>')
  if (closing < 0) throw new Error('AndroidManifest.xml has no </application>')
  manifest = `${manifest.slice(0, closing)}${service.trimStart()}\n    ${manifest.slice(closing)}`
}
const receivers = [
  ['AvailableAccountsWidget', 'available_widget'],
  ['AllAccountsWidget', 'all_widget'],
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
