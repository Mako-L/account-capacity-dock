import { HttpError, executeRequest } from '../../lib/request'
import type { ProxyConfig } from '../capacity/types'
import type { Agent, AgentStep, AgentUsage, AgentsReply, Subagent } from './types'

export const AGENTS_PORT = '8318'

// agents_server.py runs next to the proxy on the Mac, so by default it is the proxy host on port 8318.
export function defaultAgentsUrl(proxyBase: string): string {
  const parsed = new URL(proxyBase)
  parsed.port = AGENTS_PORT
  return `${parsed.protocol}//${parsed.host}`
}

type Raw = Record<string, unknown>
const text = (value: unknown) => (typeof value === 'string' && value ? value : null)
const number = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? value : null)
const list = (value: unknown): Raw[] => (Array.isArray(value) ? value.filter((item) => item && typeof item === 'object') : [])

function steps(value: unknown): AgentStep[] {
  return list(value).map((step) => ({ title: text(step.title), status: text(step.status), took: number(step.took), since: number(step.since) }))
}

function usage(value: unknown): AgentUsage | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Raw
  return {
    input: number(raw.input),
    output: number(raw.output),
    cacheRead: number(raw.cacheRead),
    cacheWrite: number(raw.cacheWrite),
    cost: number(raw.cost),
    weekPercent: number(raw.weekPercent),
  }
}

function subagent(raw: Raw): Subagent {
  return {
    id: String(raw.id ?? ''),
    name: text(raw.name),
    description: text(raw.description),
    model: text(raw.model),
    running: raw.running === true,
    idle: raw.idle === true,
    step: text(raw.step),
    updated: number(raw.updated),
    kind: text(raw.kind),
    progress: number(raw.progress),
    phase: text(raw.phase),
    summary: text(raw.summary),
    steps: steps(raw.steps),
    children: number(raw.children) ?? 0,
  }
}

function clean(raw: Raw): Agent {
  const count = raw.stepCount
  return {
    id: String(raw.id ?? ''),
    agent: String(raw.agent ?? 'claude'),
    name: text(raw.name),
    tabName: text(raw.tabName),
    project: text(raw.project),
    status: String(raw.status ?? 'idle'),
    title: text(raw.title),
    task: text(raw.task),
    now: text(raw.now),
    progress: number(raw.progress),
    stepCount: Array.isArray(count) && count.length === 2 ? [Number(count[0]), Number(count[1])] : null,
    updated: number(raw.updated),
    started: number(raw.started),
    steps: steps(raw.steps),
    subagents: list(raw.subagents).map(subagent),
    activity: list(raw.activity).map((event) => ({ at: number(event.at), text: text(event.text) ?? '', kind: text(event.kind) })),
    usage: usage(raw.usage),
    totalUsage: usage(raw.totalUsage),
  }
}

export async function fetchAgents(agentsUrl: string, config: ProxyConfig): Promise<AgentsReply> {
  try {
    const reply = await executeRequest<{ at?: number; agents?: Record<string, unknown>[] }>(`${agentsUrl}/v0/agents`, {
      headers: { Authorization: `Bearer ${config.key}` },
      timeoutMs: 15000,
    })
    return { at: reply.at ?? null, agents: (reply.agents ?? []).map(clean).filter((agent) => agent.id) }
  } catch (error) {
    if (error instanceof HttpError && error.status === 401) throw new Error('The agents server refused the management key.')
    if (error instanceof HttpError && error.status > 0) throw new Error(`The agents server answered HTTP ${error.status}.`)
    throw new Error(`No agents server at ${agentsUrl}. Run agents_server.py on the Mac.`)
  }
}
