import { Link } from 'one'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { agentSignal, agentState, currentStep, displayName, heading, progressLabel, provider, ring, stepText } from '../features/agents/rules'
import type { Agent } from '../features/agents/types'
import { AgentRing } from './AgentRing'
import { SubagentList } from './SubagentList'
import { palette } from './palette'

export function AgentRow({ agent }: { agent: Agent }) {
  const signal = agentSignal(agent)
  const color = palette.signal[signal]
  const detail = [displayName(agent), agentState(agent), stepText(agent)].filter(Boolean).join(' · ')
  const step = currentStep(agent)
  return (
    <View style={styles.card}>
    <Link href={`/agent/${encodeURIComponent(agent.id)}`} asChild>
      <Pressable style={styles.row} accessibilityLabel={`${heading(agent)}, ${agentState(agent)}, ${progressLabel(agent)}`}>
        <AgentRing ring={ring(agent)} signal={signal} working={agent.status === 'working'} provider={provider(agent)} size={48} />
        <View style={styles.text}>
          <Text style={styles.heading} numberOfLines={1}>
            {heading(agent)}
          </Text>
          <Text style={styles.secondary} numberOfLines={1}>
            {detail}
          </Text>
          {step ? (
            <Text style={styles.step} numberOfLines={1}>
              {step}
            </Text>
          ) : null}
        </View>
        <Text style={[styles.percent, { color }]}>{progressLabel(agent)}</Text>
      </Pressable>
    </Link>
      {agent.subagents.length ? <SubagentList subagents={agent.subagents} showSteps /> : null}
    </View>
  )
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    marginVertical: 5,
    padding: 14,
    gap: 4,
    borderRadius: 16,
    backgroundColor: palette.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.cardBorder,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  text: { flex: 1, gap: 2 },
  heading: { color: palette.text, fontSize: 16, fontWeight: '600' },
  secondary: { color: palette.secondary, fontSize: 13 },
  step: { color: palette.text, fontSize: 13, opacity: 0.8 },
  percent: { fontSize: 18, fontWeight: '600', fontVariant: ['tabular-nums'] },
})
