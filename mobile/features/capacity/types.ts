import type { SharedAgent } from '../agents/types'

export type Provider = 'Claude' | 'Codex'

export type Status = 'live' | 'loginRequired' | 'rateLimited' | 'stale' | 'unavailable' | 'disabled' | 'unknown'

/** What this account used inside one quota window, from the proxy's usage tracker (dock: WindowSpend). */
export type WindowSpend = { tokens: number | null; costUsd: number | null; planPercent: number | null }

export type CapacityWindow = {
  label: string
  used: number
  resetAt: number | null
  detail?: string | null
  spent?: WindowSpend | null
  usedUpIn?: number | null
  fullIn?: number | null
  atReset?: number | null
}

/** The dock's local usage block: tokens and API-equivalent cost (dock: LocalUsage). */
export type LocalUsage = {
  tokens: number | null
  inputTokens: number | null
  outputTokens: number | null
  cacheReadTokens: number | null
  cacheWriteTokens: number | null
  costUsd: number | null
  estimated: boolean | null
  unpricedModels: number | null
  status: string
  fetchedAt: number | null
  message: string | null
  scope: string | null
}

export type CapacityAccount = {
  id: string
  provider: Provider
  email: string
  title: string
  plan: string
  source: string
  /** the proxy's own view of the login: active, error, disabled */
  proxyStatus: string
  status: Status
  message: string
  windows: CapacityWindow[]
  fetchedAt: number | null
  localUsage: LocalUsage | null
  onDemandUsd: number | null
}

export type ProxyConfig = { baseUrl: string; key: string }

/** What the widget and the watch read; no emails beyond the display name, never a key. */
export type SharedSnapshot = {
  updatedAt: number
  agents?: SharedAgent[]
  accounts: Array<{
    id: string
    provider: Provider
    email: string
    used: number | null
    window: string
    resetAt: number | null
    state: string
    signal: Signal
    /** still has usage left: connected and under 100% in every window */
    available: boolean
    /** the dock's local usage tokens and API-equivalent cost */
    tokens: number | null
    costUsd: number | null
  }>
}

export type Signal = 'green' | 'yellow' | 'orange' | 'red'
