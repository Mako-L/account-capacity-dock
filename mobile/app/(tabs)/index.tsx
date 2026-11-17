import { Link } from 'one'
import { useEffect } from 'react'
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native'
import { AccountRow } from '../../components/AccountRow'
import { palette } from '../../components/palette'
import { byConstraint } from '../../features/capacity/rules'
import { refresh, useCapacity } from '../../features/capacity/store'

export default function Accounts() {
  const capacity = useCapacity()

  useEffect(() => {
    refresh()
  }, [])

  if (capacity.configured === false) {
    return (
      <View style={styles.empty}>
        <Text style={styles.title}>Connect your proxy</Text>
        <Text style={styles.body}>Add the CLIProxyAPI address and management key the dock uses.</Text>
        <Link href="/settings" asChild>
          <Pressable style={styles.button}>
            <Text style={styles.buttonText}>Open settings</Text>
          </Pressable>
        </Link>
      </View>
    )
  }

  return (
    <FlatList
      style={styles.list}
      contentInsetAdjustmentBehavior="automatic"
      data={byConstraint(capacity.accounts)}
      keyExtractor={(account) => account.id}
      renderItem={({ item }) => <AccountRow account={item} />}
      refreshControl={
        <RefreshControl refreshing={capacity.loading} onRefresh={refresh} tintColor={palette.text} />
      }
      ListHeaderComponent={
        <View style={styles.header}>
          <Text style={styles.meta}>
            {capacity.updatedAt ? `Updated ${new Date(capacity.updatedAt * 1000).toLocaleTimeString()}` : 'Loading…'}
          </Text>
          <Link href="/settings" asChild>
            <Pressable hitSlop={12}>
              <Text style={styles.link}>Proxy</Text>
            </Pressable>
          </Link>
        </View>
      }
      ListEmptyComponent={
        capacity.loading ? undefined : (
          <Text style={[styles.body, styles.padded]}>{capacity.error ?? 'The proxy has no Claude or Codex logins.'}</Text>
        )
      }
      ListFooterComponent={
        capacity.error && capacity.accounts.length ? <Text style={[styles.error, styles.padded]}>{capacity.error}</Text> : undefined
      }
    />
  )
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: palette.background },
  header: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 8 },
  meta: { color: palette.secondary, fontSize: 13 },
  link: { color: palette.link, fontSize: 15 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12, backgroundColor: palette.background },
  title: { color: palette.text, fontSize: 22, fontWeight: '600' },
  body: { color: palette.secondary, fontSize: 15, textAlign: 'center' },
  padded: { padding: 24 },
  error: { color: palette.danger, fontSize: 13, textAlign: 'center' },
  button: { backgroundColor: palette.card, borderRadius: 12, paddingHorizontal: 20, paddingVertical: 12 },
  buttonText: { color: palette.link, fontSize: 16, fontWeight: '600' },
})
