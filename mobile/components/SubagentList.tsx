import { StyleSheet, Text, View } from 'react-native'
import { subHeading, subLine, subSignal } from '../features/agents/rules'
import type { Subagent } from '../features/agents/types'
import { palette, signalColor } from './palette'

const MARK: Record<string, string> = { done: '✓', active: '›', pending: '·' }

// The dock's SubagentList: consecutive subagents of one phase share a header with a done count.
function groups(subagents: Subagent[]): { phase: string | null; subs: Subagent[] }[] {
  const result: { phase: string | null; subs: Subagent[] }[] = []
  for (const sub of subagents) {
    const last = result[result.length - 1]
    if (last && last.phase === sub.phase) last.subs.push(sub)
    else result.push({ phase: sub.phase, subs: [sub] })
  }
  return result
}

export function SubagentList({ subagents, showSteps }: { subagents: Subagent[]; showSteps: boolean }) {
  if (!subagents.length) return null
  const running = subagents.filter((sub) => sub.running).length
  return (
    <View style={styles.list}>
      <Text style={styles.section}>
        Subagents · {subagents.length}
        {running ? `, ${running} running` : ''}
      </Text>
      {groups(subagents).map((group, index) => (
        <View key={`${index}-${group.phase}`}>
          {group.phase ? (
            <Text style={[styles.phase, group.subs.some((sub) => sub.running) && { color: signalColor('yellow') }]}>
              {group.phase.toUpperCase()}
              <Text style={styles.phaseCount}>
                {'  '}
                {group.subs.filter((sub) => !sub.running).length}/{group.subs.length} done
              </Text>
            </Text>
          ) : null}
          {group.subs.map((sub) => (
            <View key={sub.id} style={styles.sub}>
              <View style={styles.subHead}>
                <View style={[styles.dot, { backgroundColor: signalColor(subSignal(sub)) }]} />
                <Text style={styles.subTitle} numberOfLines={2}>
                  {subHeading(sub)}
                  {sub.model ? <Text style={styles.model}>  {sub.model}</Text> : null}
                </Text>
                {sub.progress !== null ? (
                  <Text style={[styles.small, { color: signalColor(subSignal(sub)) }]}>{Math.floor(sub.progress)}%</Text>
                ) : null}
              </View>
              <Text style={[styles.small, styles.indent]} numberOfLines={2}>
                {subLine(sub)}
              </Text>
              {showSteps
                ? sub.steps.map((step, stepIndex) => (
                    <Text key={`${stepIndex}-${step.title}`} style={[styles.small, styles.indent, step.status === 'pending' && styles.pending]} numberOfLines={2}>
                      {MARK[step.status ?? 'pending'] ?? '·'} {step.title ?? 'Untitled step'}
                    </Text>
                  ))
                : null}
            </View>
          ))}
        </View>
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  list: { gap: 4 },
  section: { color: palette.secondary, fontSize: 11, fontWeight: '700', letterSpacing: 0.6, marginTop: 6 },
  phase: { color: palette.secondary, fontSize: 10, fontWeight: '700', marginTop: 6, marginLeft: 4 },
  phaseCount: { fontWeight: '400' },
  sub: { paddingVertical: 4, gap: 2 },
  subHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  subTitle: { flex: 1, color: palette.text, fontSize: 13 },
  model: { color: palette.secondary, fontSize: 11 },
  small: { color: palette.secondary, fontSize: 12 },
  indent: { marginLeft: 15 },
  pending: { opacity: 0.6 },
})
