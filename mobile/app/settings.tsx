import { router } from 'one'
import { useEffect, useState } from 'react'
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { palette } from '../components/palette'
import { clearConfig, hasSavedKey, saveConfig, savedKey, savedUrl } from '../features/capacity/config'
import { checkConnection, normaliseUrl } from '../features/capacity/proxy'
import { refresh } from '../features/capacity/store'

export default function Settings() {
  const [url, setUrl] = useState(savedUrl() || (Platform.OS === 'ios' ? 'http://127.0.0.1:8317' : ''))
  const [key, setKey] = useState('')
  const [keySaved, setKeySaved] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    hasSavedKey().then(setKeySaved)
  }, [])

  async function save() {
    setBusy(true)
    setStatus(null)
    try {
      const base = normaliseUrl(url)
      const secret = key || (await savedKey())
      if (!secret) throw new Error('Enter the management key.')
      const count = await checkConnection({ baseUrl: base, key: secret })
      await saveConfig(base, key || null)
      setKey('')
      setKeySaved(true)
      setStatus(`Connected: ${count} logins found.`)
      await refresh()
      router.back()
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not reach the proxy.')
    } finally {
      setBusy(false)
    }
  }

  async function forget() {
    await clearConfig()
    setKeySaved(false)
    setStatus('Proxy address and key removed from this device.')
    await refresh()
  }

  return (
    <View style={styles.screen}>
      <Text style={styles.label}>Proxy address</Text>
      <TextInput
        style={styles.input}
        value={url}
        onChangeText={setUrl}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        placeholder="http://100.x.y.z:8317"
        placeholderTextColor={palette.secondary}
      />
      <Text style={styles.hint}>
        The CLIProxyAPI base, for example the Mac's LAN or Tailscale address. Its panel is this address + /management.html.
      </Text>
      <Text style={styles.label}>Management key</Text>
      <TextInput
        style={styles.input}
        value={key}
        onChangeText={setKey}
        secureTextEntry
        autoCapitalize="none"
        autoCorrect={false}
        placeholder={keySaved ? 'Saved in secure storage' : 'Management key'}
        placeholderTextColor={palette.secondary}
      />
      <Text style={styles.hint}>Stored only in the device's secure storage (Keychain or Android Keystore).</Text>
      <Pressable style={[styles.button, busy && styles.disabled]} onPress={save} disabled={busy}>
        <Text style={styles.buttonText}>{busy ? 'Checking…' : 'Save and connect'}</Text>
      </Pressable>
      {keySaved ? (
        <Pressable onPress={forget} hitSlop={8}>
          <Text style={styles.danger}>Forget this proxy</Text>
        </Pressable>
      ) : null}
      {status ? <Text style={styles.status}>{status}</Text> : null}
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background, padding: 20, gap: 8 },
  label: { color: palette.text, fontSize: 15, fontWeight: '600', marginTop: 12 },
  input: {
    color: palette.text,
    backgroundColor: palette.card,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.cardBorder,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
  hint: { color: palette.secondary, fontSize: 12 },
  button: { marginTop: 20, backgroundColor: palette.link, borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  disabled: { opacity: 0.5 },
  buttonText: { color: palette.text, fontSize: 16, fontWeight: '600' },
  danger: { color: palette.danger, fontSize: 15, textAlign: 'center', marginTop: 16 },
  status: { color: palette.secondary, fontSize: 13, textAlign: 'center', marginTop: 12 },
})
