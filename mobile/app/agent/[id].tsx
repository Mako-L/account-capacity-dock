import { useParams } from 'one'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { AgentRing } from '../../components/AgentRing'
import { palette, signalColor } from '../../components/palette'
import {
  agentSignal,
  agentState,
  currentStep,
  displayName,
  heading,
  progressLabel,
  provider,
  ring,
  sinceText,
  stepText,
} from '../../features/agents/rules'
import { agentById, useAgents } from '../../features/agents/store'

const MARK: Record<string, string> = { done: '✓', active: '›', pending: '·' }

export default function AgentDetail() {
  const { id } = useParams<{ id: string }>()
  useAgents()
  const agent = agentById(String(id))

  if (!agent) {
    return (
      <View style={[styles.screen, styles.center]}>
        <Text style={styles.secondary}>This agent is no longer in the Mac's snapshot.</Text>
      </View>
    )
  }

  const signal = agentSignal(agent)
  const color = signalColor(signal)
  const facts = [
    provider(agent),
    agentState(agent),
    stepText(agent),
    agent.subagents.running ? `${agent.subagents.running} subagents running` : '',
    agent.updated ? `updated ${sinceText(agent.updated)}` : '',
  ].filter(Boolean)

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.hero}>
        <AgentRing ring={ring(agent)} signal={signal} working={agent.status === 'working'} provider={provider(agent)} size={120} />
        <Text style={[styles.percent, { color }]}>{progressLabel(agent)}</Text>
        <Text style={styles.name}>{displayName(agent)}</Text>
        <Text style={styles.heading}>{heading(agent)}</Text>
        {currentStep(agent) ? <Text style={styles.now}>{currentStep(agent)}</Text> : null}
        <Text style={styles.secondary}>{facts.join(' · ')}</Text>
      </View>
      {agent.steps.map((step, index) => (
        <View key={`${index}-${step.title}`} style={styles.step}>
          <Text style={[styles.mark, step.status === 'done' && { color: signalColor('green') }, step.status === 'active' && { color }]}>
            {MARK[step.status ?? 'pending'] ?? '·'}
          </Text>
          <Text style={[styles.stepText, step.status === 'pending' && styles.secondary]}>{step.title ?? 'Untitled step'}</Text>
        </View>
      ))}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  center: { alignItems: 'center', justifyContent: 'center', padding: 24 },
  content: { padding: 16, gap: 8 },
  hero: { alignItems: 'center', gap: 6, paddingVertical: 16 },
  percent: { fontSize: 34, fontWeight: '700', fontVariant: ['tabular-nums'] },
  name: { color: palette.text, fontSize: 20, fontWeight: '600' },
  heading: { color: palette.text, fontSize: 15, textAlign: 'center' },
  now: { color: palette.secondary, fontSize: 14, textAlign: 'center', fontStyle: 'italic' },
  secondary: { color: palette.secondary, fontSize: 13, textAlign: 'center' },
  step: {
    flexDirection: 'row',
    gap: 10,
    backgroundColor: palette.card,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.cardBorder,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  mark: { color: palette.secondary, fontSize: 16, width: 14, textAlign: 'center' },
  stepText: { color: palette.text, fontSize: 14, flex: 1 },
})
