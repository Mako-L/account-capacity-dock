import type { Agent, AgentSignal, SharedAgent } from './types'

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

// The dock hides idle agents unless Settings shows them.
export function visibleAgents(agents: Agent[], showIdle: boolean): Agent[] {
  return showIdle ? agents : agents.filter((agent) => agent.status !== 'idle')
}

const ORDER: Record<string, number> = { blocked: 0, working: 1, done: 2, idle: 3 }

// Needs you first, then working, finished, idle; newest activity first inside each.
export function byAttention(agents: Agent[]): Agent[] {
  return [...agents].sort(
    (left, right) =>
      (ORDER[left.status] ?? 4) - (ORDER[right.status] ?? 4) || (right.updated ?? 0) - (left.updated ?? 0),
  )
}

export function toSharedAgents(agents: Agent[], limit = 8): SharedAgent[] {
  return byAttention(agents.filter((agent) => agent.status !== 'idle'))
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
    }))
}

export function sinceText(timestamp: number | null, now = Date.now() / 1000): string {
  if (timestamp === null) return ''
  const seconds = Math.max(0, Math.floor(now - timestamp))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}
