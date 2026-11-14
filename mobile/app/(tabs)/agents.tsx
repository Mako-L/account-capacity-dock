import { Link } from 'one'
import { useEffect } from 'react'
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native'
import { AgentRow } from '../../components/AgentRow'
import { palette } from '../../components/palette'
import { byAttention } from '../../features/agents/rules'
import { refreshAgents, useAgents } from '../../features/agents/store'

// The dock reruns agents.py every 6 s; the phone polls the Mac's snapshot about as often while this tab is open.
const POLL_MS = 10000

export default function Agents() {
  const state = useAgents()

  useEffect(() => {
    refreshAgents()
    const timer = setInterval(refreshAgents, POLL_MS)
    return () => clearInterval(timer)
  }, [])

  if (state.configured === false) {
    return (
      <View style={styles.empty}>
        <Text style={styles.title}>Connect your proxy</Text>
        <Text style={styles.body}>The agents panel uses the same address and management key as the accounts.</Text>
        <Link href="/settings" asChild>
          <Pressable style={styles.button}>
            <Text style={styles.buttonText}>Open settings</Text>
          </Pressable>
        </Link>
      </View>
    )
  }

  const agents = byAttention(state.agents)
  const working = agents.filter((agent) => agent.status === 'working' || agent.status === 'blocked').length

  return (
    <FlatList
      style={styles.list}
      contentInsetAdjustmentBehavior="automatic"
      data={agents}
      keyExtractor={(agent) => agent.id}
      renderItem={({ item }) => <AgentRow agent={item} />}
      refreshControl={
        <RefreshControl refreshing={state.loading && !state.agents.length} onRefresh={refreshAgents} tintColor={palette.text} />
      }
      ListHeaderComponent={
        <View style={styles.header}>
          <Text style={styles.meta}>
            {state.at ? `Mac snapshot ${new Date(state.at * 1000).toLocaleTimeString()}` : 'Loading…'}
          </Text>
          <Text style={styles.meta}>
            {agents.length} agents · {working} working
          </Text>
        </View>
      }
      ListEmptyComponent={
        state.loading && !state.at ? undefined : (
          <View style={styles.padded}>
            <Text style={styles.body}>
              {state.error ?? 'No agents on the Mac.'}
            </Text>
          </View>
        )
      }
      ListFooterComponent={
        state.error && agents.length ? <Text style={[styles.error, styles.padded]}>{state.error}</Text> : undefined
      }
    />
  )
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: palette.background },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  meta: { color: palette.secondary, fontSize: 13 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12, backgroundColor: palette.background },
  title: { color: palette.text, fontSize: 22, fontWeight: '600' },
  body: { color: palette.secondary, fontSize: 15, textAlign: 'center' },
  padded: { padding: 24 },
  error: { color: palette.danger, fontSize: 13, textAlign: 'center' },
  button: { backgroundColor: palette.card, borderRadius: 12, paddingHorizontal: 20, paddingVertical: 12 },
  buttonText: { color: palette.link, fontSize: 16, fontWeight: '600' },
})
