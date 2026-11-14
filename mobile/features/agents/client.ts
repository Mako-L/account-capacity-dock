import { HttpError, executeRequest } from '../../lib/request'
import type { ProxyConfig } from '../capacity/types'
import type { Agent, AgentsReply } from './types'

export const AGENTS_PORT = '8318'

// agents_server.py runs next to the proxy on the Mac, so by default it is the proxy host on port 8318.
export function defaultAgentsUrl(proxyBase: string): string {
  const parsed = new URL(proxyBase)
  parsed.port = AGENTS_PORT
  return `${parsed.protocol}//${parsed.host}`
}

function clean(raw: Record<string, unknown>): Agent {
  const text = (value: unknown) => (typeof value === 'string' && value ? value : null)
  const number = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? value : null)
  const count = raw.stepCount
  const subagents = (raw.subagents ?? {}) as Record<string, unknown>
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
    steps: (Array.isArray(raw.steps) ? raw.steps : []).map((step: Record<string, unknown>) => ({
      title: text(step?.title),
      status: text(step?.status),
    })),
    subagents: { running: number(subagents.running) ?? 0, total: number(subagents.total) ?? 0 },
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
