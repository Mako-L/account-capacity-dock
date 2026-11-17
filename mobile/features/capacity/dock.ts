import { HttpError, executeRequest } from '../../lib/request'
import { defaultAgentsUrl } from '../agents/client'
import type { CapacityAccount, CapacityWindow, LocalUsage, Provider, ProxyConfig, Status } from './types'

type Raw = Record<string, unknown>

const STATUSES: Status[] = ['live', 'loginRequired', 'rateLimited', 'stale', 'unavailable', 'disabled', 'unknown']
const text = (value: unknown) => (typeof value === 'string' ? value : '')
const number = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? value : null)

function window(raw: Raw): CapacityWindow {
  const spent = raw.spent as Raw | null | undefined
  return {
    label: text(raw.label),
    used: number(raw.used) ?? 0,
    resetAt: number(raw.resetAt),
    detail: text(raw.detail) || null,
    spent: spent ? { tokens: number(spent.tokens), costUsd: number(spent.costUsd), planPercent: number(spent.planPercent) } : null,
    usedUpIn: number(raw.usedUpIn),
    fullIn: number(raw.fullIn),
    atReset: number(raw.atReset),
  }
}

function usage(raw: Raw | null | undefined): LocalUsage | null {
  if (!raw) return null
  return {
    tokens: number(raw.tokens),
    inputTokens: number(raw.inputTokens),
    outputTokens: number(raw.outputTokens),
    cacheReadTokens: number(raw.cacheReadTokens),
    cacheWriteTokens: number(raw.cacheWriteTokens),
    costUsd: number(raw.costUsd),
    estimated: typeof raw.estimated === 'boolean' ? raw.estimated : null,
    unpricedModels: number(raw.unpricedModels),
    status: text(raw.status),
    fetchedAt: number(raw.fetchedAt),
    message: text(raw.message) || null,
    scope: text(raw.scope) || null,
  }
}

export function dockAccount(raw: Raw): CapacityAccount {
  const status = STATUSES.includes(raw.status as Status) ? (raw.status as Status) : 'unknown'
  return {
    id: text(raw.id),
    provider: text(raw.provider) as Provider,
    email: text(raw.email),
    title: text(raw.title) || text(raw.email).split('@')[0],
    plan: text(raw.plan),
    source: text(raw.source),
    proxyStatus: status,
    status,
    message: text(raw.message),
    windows: ((raw.windows as Raw[]) ?? []).map(window),
    fetchedAt: number(raw.fetchedAt),
    localUsage: usage(raw.localUsage as Raw | null),
    onDemandUsd: number(raw.onDemandUsd),
  }
}

// The dock's own account snapshot from agents_server.py, so pace, spend and local usage match the Mac exactly.
export async function fetchDockAccounts(config: ProxyConfig): Promise<CapacityAccount[] | null> {
  try {
    const reply = await executeRequest<{ accounts?: Raw[] }>(`${defaultAgentsUrl(config.baseUrl)}/v0/capacity`, {
      headers: { Authorization: `Bearer ${config.key}` },
      timeoutMs: 10000,
    })
    return reply.accounts?.length ? reply.accounts.map(dockAccount) : null
  } catch (error) {
    if (error instanceof HttpError) return null
    throw error
  }
}
