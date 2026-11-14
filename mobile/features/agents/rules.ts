import { ago } from '../capacity/format'
import type { Agent, AgentSignal, SharedAgent, Subagent } from './types'

// Ports of AgentItem in AgentDock.swift, so the phone reads agents the way the dock does.
export function provider(agent: Agent): 'Claude' | 'Codex' {
  return agent.agent === 'codex' ? 'Codex' : 'Claude'
}

export function heading(agent: Agent): string {
  return agent.task || agent.title || agent.name || provider(agent)
}

export function displayName(agent: Agent): string {
  return agent.name || agent.tabName || agent.project || provider(agent)
}

export function isLive(agent: Agent): boolean {
  return agent.status === 'working' || agent.status === 'blocked'
}

// Yellow while it works, red when it needs you, green when it finished.
export function agentSignal(agent: Agent): AgentSignal {
  if (agent.status === 'working') return 'yellow'
  if (agent.status === 'blocked') return 'red'
  if (agent.status === 'done') return 'green'
  return 'gray'
}

export function agentState(agent: Agent): string {
  if (agent.status === 'working') return 'Working'
  if (agent.status === 'blocked') return 'Needs you'
  if (agent.status === 'done') return 'Finished'
  return 'Idle'
}

// Progress when known, full when finished, a short arc while it works.
export function ring(agent: Agent): number {
  if (agent.progress !== null && Number.isFinite(agent.progress)) return Math.min(100, Math.max(0, agent.progress))
  if (agent.status === 'done') return 100
  return isLive(agent) ? 8 : 0
}

export function stepCount(agent: Agent): [number, number] | null {
  if (agent.stepCount) return agent.stepCount
  if (!agent.steps.length) return null
  return [agent.steps.filter((step) => step.status === 'done').length, agent.steps.length]
}

export function stepText(agent: Agent): string {
  const count = stepCount(agent)
  return count ? `${count[0]}/${count[1]} steps` : ''
}

// The step the agent is on: the observer's "now", else the first unfinished step.
export function currentStep(agent: Agent): string {
  if (agent.now) return agent.now
  const active = agent.steps.find((step) => step.status && step.status !== 'done')
  return active?.title ?? ''
}

export function progressLabel(agent: Agent): string {
  return agent.progress === null ? agentState(agent) : `${Math.floor(agent.progress)}%`
}

const ORDER: Record<string, number> = { blocked: 0, working: 1, done: 2, idle: 3 }

// Needs you first, then working, finished, idle; newest activity first inside each.
export function byAttention(agents: Agent[]): Agent[] {
  return [...agents].sort(
    (left, right) =>
      (ORDER[left.status] ?? 4) - (ORDER[right.status] ?? 4) || (right.updated ?? 0) - (left.updated ?? 0),
  )
}

// Every agent, idle and finished ones included, as the dock shows them; working ones sort first.
export function toSharedAgents(agents: Agent[], limit = 60): SharedAgent[] {
  return byAttention(agents)
    .slice(0, limit)
    .map((agent) => ({
      id: agent.id,
      provider: provider(agent),
      name: displayName(agent),
      heading: heading(agent),
      step: currentStep(agent),
      progress: agent.progress,
      ring: ring(agent),
      status: agent.status,
      state: agentState(agent),
      signal: agentSignal(agent),
      subagents: agent.subagents.length,
      runningSubagents: agent.subagents.filter((sub) => sub.running).length,
    }))
}

export function subSignal(sub: Subagent): AgentSignal {
  return sub.running ? 'yellow' : sub.idle ? 'gray' : 'green'
}

// The dock's SubagentList heading: a workflow by its name, a subagent by its description.
export function subHeading(sub: Subagent): string {
  return sub.kind === 'workflow' ? (sub.name ?? 'Workflow') : (sub.description ?? sub.name ?? 'Subagent')
}

export function subLine(sub: Subagent, now = Date.now() / 1000): string {
  const done = sub.steps.filter((step) => step.status === 'done').length
  const count = sub.kind === 'workflow' ? sub.summary : sub.steps.length ? `${done}/${sub.steps.length} steps` : null
  const state = sub.running ? `▸ ${sub.step ?? 'Working'}` : sub.idle ? 'Idle' : 'Finished'
  const kids = sub.kind === 'workflow' ? 0 : sub.children
  return [state, count, ago(sub.updated, now), kids > 0 ? `${kids} inside` : null].filter(Boolean).join(' · ')
}

export function sinceText(timestamp: number | null, now = Date.now() / 1000): string {
  if (timestamp === null) return ''
  const seconds = Math.max(0, Math.floor(now - timestamp))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}
