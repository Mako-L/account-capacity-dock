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
import { span } from '../../features/capacity/format'
import { agentById, useAgents } from '../../features/agents/store'
import { SubagentList } from '../../components/SubagentList'
import { ago, runTime, usageLine } from '../../features/capacity/format'

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
    agent.updated ? `updated ${sinceText(agent.updated)}` : '',
  ].filter(Boolean)
  const names = [...new Set([agent.name, agent.tabName].filter(Boolean))].join(' · ')
  const started = agent.started ? `Started ${new Date(agent.started * 1000).toLocaleString()}` : null
  const updated = agent.updated ? `Updated ${new Date(agent.updated * 1000).toLocaleString()}` : null
  const own = usageLine(agent.usage)
  const total = usageLine(agent.totalUsage)
  const time = [runTime(agent.started, agent.updated, agent.status === 'working' || agent.status === 'blocked'), ago(agent.updated)]
    .filter(Boolean)
    .join(' · ')

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.hero}>
        <AgentRing ring={ring(agent)} signal={signal} working={agent.status === 'working'} provider={provider(agent)} size={120} />
        <Text style={[styles.percent, { color }]}>{progressLabel(agent)}</Text>
        <Text style={styles.name}>{names || displayName(agent)}</Text>
        <Text style={styles.heading}>{heading(agent)}</Text>
        {currentStep(agent) ? <Text style={styles.now}>{currentStep(agent)}</Text> : null}
        <Text style={styles.secondary}>{facts.join(' · ')}</Text>
        {agent.project ? <Text style={styles.secondary}>Project {agent.project}</Text> : null}
      </View>
      {agent.steps.length ? (
        <Text style={styles.section}>{stepText(agent) ? `Steps · ${stepText(agent).replace(' steps', '')}` : 'Steps'}</Text>
      ) : null}
      {agent.steps.map((step, index) => (
        <View key={`${index}-${step.title}`} style={styles.step}>
          <Text style={[styles.mark, step.status === 'done' && { color: signalColor('green') }, step.status === 'active' && { color }]}>
            {MARK[step.status ?? 'pending'] ?? '·'}
          </Text>
          <Text style={[styles.stepText, step.status === 'pending' && styles.secondary]}>{step.title ?? 'Untitled step'}</Text>
          {step.took !== null || step.since !== null ? (
            <Text style={styles.stepTime}>{step.took !== null ? span(step.took) : span(Date.now() / 1000 - (step.since ?? 0))}</Text>
          ) : null}
        </View>
      ))}
      {agent.subagents.length ? <SubagentList subagents={agent.subagents} showSteps /> : null}
      {agent.activity.length ? <Text style={styles.section}>Recent activity</Text> : null}
      {[...agent.activity].reverse().map((event, index) => (
        <View key={`${index}-${event.at}`} style={styles.activity}>
          <Text style={[styles.small, styles.activityAge]}>{ago(event.at)}</Text>
          <Text style={[styles.small, event.kind === 'say' && styles.say]} numberOfLines={1}>{event.text}</Text>
        </View>
      ))}
      {own ? <Text style={styles.section}>Tokens</Text> : null}
      {own ? <Text style={styles.small}>{own}</Text> : null}
      {own && total && total !== own ? <Text style={styles.small}>With subagents: {total}</Text> : null}
      {time ? <Text style={[styles.small, styles.footer]}>{time}</Text> : null}
      {started ? <Text style={styles.small}>{started}</Text> : null}
      {updated ? <Text style={styles.small}>{updated}</Text> : null}
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
  stepTime: { color: palette.secondary, fontSize: 12, fontVariant: ['tabular-nums'] },
  section: { color: palette.secondary, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase', marginTop: 10 },
  dot: { width: 8, height: 8, borderRadius: 4, marginTop: 6 },
  subText: { flex: 1, gap: 2 },
  model: { color: palette.secondary, fontSize: 11 },
  small: { color: palette.secondary, fontSize: 12 },
  activity: { flexDirection: 'row', gap: 8, paddingHorizontal: 4 },
  activityAge: { width: 56 },
  say: { color: palette.text },
  footer: { textAlign: 'center', marginTop: 12 },
})
