import { Stack, useParams } from 'one'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { palette, signalColor } from '../../components/palette'
import { ProviderRing } from '../../components/ProviderRing'
import { ago, dollars, formatCount, span, spendLine } from '../../features/capacity/format'
import { percentLabel, resetText, signal, stateLabel, usedPercent } from '../../features/capacity/rules'
import { useCapacity } from '../../features/capacity/store'
import type { CapacityAccount, CapacityWindow } from '../../features/capacity/types'

function barColor(used: number, provider: string) {
  if (used >= 100) return palette.signal.red
  return provider === 'Claude' ? palette.signal.orange : palette.signal.green
}

function WindowRow({ window, provider }: { window: CapacityWindow; provider: string }) {
  const lines = [
    resetText(window.resetAt),
    window.detail ?? null,
    window.spent ? spendLine(window.spent) : null,
    window.fullIn ? `At this pace, full in ${span(window.fullIn)}` : null,
    window.atReset ? `At this pace, about ${Math.floor(window.atReset)}% at the reset` : null,
    window.usedUpIn ? `Used up in ${span(window.usedUpIn)}` : null,
  ].filter((line): line is string => Boolean(line))
  return (
    <View style={styles.window}>
      <View style={styles.row}>
        <Text style={styles.windowLabel}>{window.label}</Text>
        <Text style={styles.windowUsed}>{Math.floor(window.used)}% used</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${Math.min(100, window.used)}%`, backgroundColor: barColor(window.used, provider) }]} />
      </View>
      {lines.map((line) => (
        <Text key={line} style={styles.small}>
          {line}
        </Text>
      ))}
    </View>
  )
}

function UsageBlock({ account }: { account: CapacityAccount }) {
  const usage = account.localUsage
  const perAccount = usage?.scope === 'account'
  const breakdown =
    usage && usage.tokens !== null
      ? `Input ${formatCount(usage.inputTokens ?? 0)} · Output ${formatCount(usage.outputTokens ?? 0)}\nCache read ${formatCount(usage.cacheReadTokens ?? 0)} · Write ${formatCount(usage.cacheWriteTokens ?? 0)}`
      : null
  return (
    <View style={styles.card}>
      <Text style={styles.section}>{perAccount ? 'Last 24 h · this account' : `Today · local ${account.provider} usage`}</Text>
      <View style={styles.row}>
        <Text style={styles.body}>Tokens{usage?.estimated ? ' (estimated)' : ''}</Text>
        <Text style={styles.value}>{usage?.tokens != null ? formatCount(usage.tokens) : '—'}</Text>
      </View>
      <View style={styles.row}>
        <Text style={styles.body}>API-equivalent cost</Text>
        <Text style={styles.value}>{usage?.costUsd != null ? dollars(usage.costUsd) : '—'}</Text>
      </View>
      {breakdown ? <Text style={styles.small}>{breakdown}</Text> : null}
      <Text style={styles.small}>
        {perAccount ? 'Proxy usage tracker · CodeBurn prices · not your bill' : 'CodeBurn · all local accounts · not your bill'}
      </Text>
      {usage && usage.status !== 'live' ? (
        <Text style={styles.small}>
          {usage.status === 'partial' ? 'Indexing · totals are incomplete' : usage.message || `Cached · ${ago(usage.fetchedAt)}`}
        </Text>
      ) : null}
      {(usage?.unpricedModels ?? 0) > 0 ? <Text style={styles.small}>Some models have no price; cost is incomplete.</Text> : null}
      {!usage ? <Text style={styles.small}>Usage comes from the Mac dock; start agents_server.py to see it here.</Text> : null}
      {account.onDemandUsd !== null ? (
        <View style={styles.row}>
          <Text style={styles.body}>On-demand · billing cycle</Text>
          <Text style={styles.value}>{dollars(account.onDemandUsd)}</Text>
        </View>
      ) : null}
    </View>
  )
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
  const tone = signalColor(signal(account))
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
      <Stack.Screen options={{ title: account.title || account.provider }} />
      <View style={styles.hero}>
        <ProviderRing account={account} size={120} />
        <Text style={[styles.percent, { color: tone }]}>{percentLabel(used)}</Text>
        <Text style={styles.email}>{account.email}</Text>
        <Text style={styles.secondary}>
          {[account.provider === 'Claude' || !account.plan ? account.provider : account.plan, account.source].filter(Boolean).join(' · ')}
          {'  '}
          <Text style={{ color: tone }}>{stateLabel(account)}</Text>
        </Text>
      </View>
      {account.windows.length ? (
        account.windows.map((window) => <WindowRow key={window.label} window={window} provider={account.provider} />)
      ) : (
        <Text style={[styles.secondary, styles.centered]}>{account.message || 'Capacity unknown'}</Text>
      )}
      {account.windows.length && account.message ? <Text style={[styles.secondary, styles.centered]}>{account.message}</Text> : null}
      <UsageBlock account={account} />
      <Text style={[styles.small, styles.centered]}>
        {account.fetchedAt ? `Read ${ago(account.fetchedAt)}` : ''}
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
  centered: { textAlign: 'center' },
  window: { gap: 5, padding: 14, borderRadius: 16, backgroundColor: palette.card },
  card: { gap: 6, padding: 14, borderRadius: 16, backgroundColor: palette.card },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  windowLabel: { color: palette.text, fontSize: 15, fontWeight: '500' },
  windowUsed: { color: palette.text, fontSize: 14, fontVariant: ['tabular-nums'] },
  track: { height: 5, borderRadius: 3, backgroundColor: palette.cardBorder, overflow: 'hidden' },
  fill: { height: 5, borderRadius: 3 },
  section: { color: palette.text, fontSize: 13, fontWeight: '600' },
  body: { color: palette.text, fontSize: 13 },
  value: { color: palette.text, fontSize: 13, fontVariant: ['tabular-nums'] },
  small: { color: palette.secondary, fontSize: 11 },
})
