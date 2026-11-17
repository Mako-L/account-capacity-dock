import { Link } from 'one'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { isConnected, limitingWindow, percentLabel, resetText, signal, stateLabel, usedPercent } from '../features/capacity/rules'
import type { CapacityAccount } from '../features/capacity/types'
import { palette, signalColor } from './palette'
import { ProviderRing } from './ProviderRing'

export function AccountRow({ account }: { account: CapacityAccount }) {
  const used = usedPercent(account)
  const limiting = limitingWindow(account)
  const connected = isConnected(account)
  return (
    <Link href={`/account/${account.id}`} asChild>
      <Pressable style={styles.row}>
        <ProviderRing account={account} size={48} />
        <View style={styles.middle}>
          <Text style={styles.email} numberOfLines={1}>{account.email}</Text>
          <Text style={styles.detail} numberOfLines={1}>
            {account.provider}{account.plan ? ` · ${account.plan}` : ''}{limiting ? ` · ${limiting.label}` : ''}
          </Text>
          <View style={styles.stateLine}>
            <View style={[styles.dot, { backgroundColor: connected ? palette.signal.green : palette.danger }]} />
            <Text style={styles.detail} numberOfLines={1}>
              {stateLabel(account)}{limiting ? ` · ${resetText(limiting.resetAt)}` : ''}
            </Text>
          </View>
        </View>
        <Text style={[styles.percent, { color: signalColor(signal(account)) }]}>{percentLabel(used)}</Text>
      </Pressable>
    </Link>
  )
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    marginHorizontal: 16,
    marginVertical: 5,
    padding: 14,
    borderRadius: 16,
    backgroundColor: palette.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.cardBorder,
  },
  middle: { flex: 1, gap: 2 },
  email: { color: palette.text, fontSize: 15, fontWeight: '600' },
  detail: { color: palette.secondary, fontSize: 12 },
  stateLine: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  percent: { fontSize: 24, fontWeight: '600', fontVariant: ['tabular-nums'] },
})
