import { Stack, useParams } from 'one'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { palette, signalColor } from '../../components/palette'
import { ProviderRing } from '../../components/ProviderRing'
import { Ring } from '../../components/Ring'
import { percentLabel, resetText, signal, stateLabel, usedPercent } from '../../features/capacity/rules'
import { useCapacity } from '../../features/capacity/store'

function windowSignal(used: number) {
  return used >= 100 ? 'red' : used >= 85 ? 'orange' : used >= 70 ? 'yellow' : 'green'
}

export default function AccountDetail() {
  const { id } = useParams<{ id: string }>()
  const capacity = useCapacity()
  const account = capacity.accounts.find((item) => item.id === id)

  if (!account) {
    return (
      <View style={styles.screen}>
        <Text style={styles.secondary}>This account is no longer on the proxy.</Text>
      </View>
    )
  }

  const used = usedPercent(account)
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
      <Stack.Screen options={{ title: account.provider }} />
      <View style={styles.hero}>
        <ProviderRing account={account} size={120} />
        <Text style={[styles.percent, { color: signalColor(signal(account)) }]}>{percentLabel(used)}</Text>
        <Text style={styles.email}>{account.email}</Text>
        <Text style={styles.secondary}>
          {[account.provider, account.plan, stateLabel(account)].filter(Boolean).join(' · ')}
        </Text>
        {account.message ? <Text style={styles.message}>{account.message}</Text> : null}
      </View>
      {account.windows.map((item) => (
        <View key={item.label} style={styles.window}>
          <Ring used={item.used} signal={windowSignal(item.used)} size={44} />
          <View style={styles.windowText}>
            <Text style={styles.windowLabel}>{item.label}</Text>
            <Text style={styles.secondary}>{resetText(item.resetAt)}</Text>
          </View>
          <Text style={[styles.windowPercent, { color: signalColor(windowSignal(item.used)) }]}>
            {percentLabel(item.used)}
          </Text>
        </View>
      ))}
      <Text style={[styles.secondary, styles.footer]}>
        Proxy login: {account.proxyStatus || 'unknown'}
        {account.fetchedAt ? ` · read ${new Date(account.fetchedAt * 1000).toLocaleTimeString()}` : ''}
      </Text>
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  content: { padding: 16, gap: 10 },
  hero: { alignItems: 'center', gap: 6, paddingVertical: 20 },
  percent: { fontSize: 44, fontWeight: '600', fontVariant: ['tabular-nums'] },
  email: { color: palette.text, fontSize: 17, fontWeight: '600' },
  secondary: { color: palette.secondary, fontSize: 13 },
  message: { color: palette.signal.orange, fontSize: 13, textAlign: 'center' },
  window: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    padding: 14,
    borderRadius: 16,
    backgroundColor: palette.card,
  },
  windowText: { flex: 1, gap: 2 },
  windowLabel: { color: palette.text, fontSize: 15, fontWeight: '500' },
  windowPercent: { fontSize: 20, fontWeight: '600', fontVariant: ['tabular-nums'] },
  footer: { textAlign: 'center', paddingTop: 12 },
})
