export type Provider = 'Claude' | 'Codex'

export type Status = 'live' | 'loginRequired' | 'rateLimited' | 'stale' | 'unavailable' | 'disabled' | 'unknown'

export type CapacityWindow = { label: string; used: number; resetAt: number | null }

export type CapacityAccount = {
  id: string
  provider: Provider
  email: string
  plan: string
  /** the proxy's own view of the login: active, error, disabled */
  proxyStatus: string
  status: Status
  message: string
  windows: CapacityWindow[]
  fetchedAt: number | null
}

export type ProxyConfig = { baseUrl: string; key: string }

/** What the widget and the watch read; no emails beyond the display name, never a key. */
export type SharedSnapshot = {
  updatedAt: number
  accounts: Array<{
    id: string
    provider: Provider
    email: string
    used: number | null
    window: string
    resetAt: number | null
    state: string
    signal: Signal
  }>
}

export type Signal = 'green' | 'yellow' | 'orange' | 'red'
