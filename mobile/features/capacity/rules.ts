import type { CapacityAccount, CapacityWindow, SharedSnapshot, Signal, Status } from './types'

type Json = Record<string, unknown>

const PLANS: Record<string, string> = { pro: 'Pro', prolite: 'Pro Lite', promax: 'Pro Max', plus: 'Plus', team: 'Team' }

// Same as collector.percentage: finite numbers clamped to 0-100, anything else is unknown.
export function percentage(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.min(100, Math.max(0, value))
}

export function timestamp(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed / 1000
}

function window(label: string, used: unknown, reset?: unknown): CapacityWindow | null {
  const value = percentage(used)
  return value === null ? null : { label, used: value, resetAt: timestamp(reset) }
}

const CLAUDE_LABELS: Record<string, string> = {
  five_hour: '5-hour',
  seven_day: 'Weekly',
  seven_day_opus: 'Weekly · Opus',
  seven_day_sonnet: 'Weekly · Sonnet',
  seven_day_oauth_apps: 'Weekly · OAuth',
}

// Port of collector.claude_windows.
export function claudeWindows(data: Json): CapacityWindow[] {
  const result: CapacityWindow[] = []
  for (const [key, label] of Object.entries(CLAUDE_LABELS)) {
    const row = data[key]
    if (row && typeof row === 'object') {
      const item = window(label, (row as Json).utilization, (row as Json).resets_at)
      if (item) result.push(item)
    }
  }
  for (const limit of (Array.isArray(data.limits) ? data.limits : []) as Json[]) {
    if (limit?.kind !== 'weekly_scoped') continue
    const model = ((limit.scope as Json | undefined)?.model as Json | undefined)?.display_name
    if (typeof model !== 'string' || result.some((existing) => existing.label === `Weekly · ${model}`)) continue
    const item = window(`Weekly · ${model}`, limit.percent, limit.resets_at)
    if (item) result.push(item)
  }
  return result
}

// Port of collector.codex_windows: Weekly sorts last.
export function codexWindows(data: Json): CapacityWindow[] {
  const result: CapacityWindow[] = []
  const rate = (data.rate_limit ?? {}) as Json
  const secondary = (data.secondary_rate_limit ?? {}) as Json
  const candidates: unknown[] = [rate.primary_window, rate.secondary_window]
  if ('used_percent' in rate) candidates.push(rate)
  candidates.push(secondary.primary_window, secondary.secondary_window)
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== 'object') continue
    const row = candidate as Json
    const seconds = row.limit_window_seconds
    const label =
      seconds === 604800 ? 'Weekly' : seconds === 18000 ? '5-hour' : seconds === 86400 ? 'Daily' : 'Quota'
    const item = window(label, row.used_percent, row.reset_at)
    if (item && !result.some((existing) => JSON.stringify(existing) === JSON.stringify(item))) result.push(item)
  }
  return [...result.filter((item) => item.label !== 'Weekly'), ...result.filter((item) => item.label === 'Weekly')]
}

export function planName(value: unknown): string {
  return typeof value === 'string' ? (PLANS[value] ?? value) : ''
}

// The dock's `used`: the highest window, so the ring shows the most constrained quota.
export function usedPercent(account: CapacityAccount): number | null {
  if (!account.windows.length) return null
  return Math.max(...account.windows.map((item) => item.used))
}

export function limitingWindow(account: CapacityAccount): CapacityWindow | null {
  return account.windows.reduce<CapacityWindow | null>(
    (best, item) => (!best || item.used > best.used ? item : best),
    null,
  )
}

// The dock's signal: Reconnect is orange; otherwise 100 red, 85 orange, 70 yellow, else green.
export function signal(account: CapacityAccount): Signal {
  if (account.status === 'loginRequired') return 'orange'
  const used = usedPercent(account) ?? 0
  if (used >= 100) return 'red'
  if (used >= 85) return 'orange'
  if (used >= 70) return 'yellow'
  return 'green'
}

const STATE_LABELS: Record<Status, string> = {
  live: 'Available',
  loginRequired: 'Reconnect',
  rateLimited: 'Throttled',
  stale: 'Cached',
  unavailable: 'Unavailable',
  disabled: 'Disabled',
  unknown: 'Unknown',
}

export function stateLabel(account: CapacityAccount): string {
  if (account.status === 'live' && (usedPercent(account) ?? 0) >= 100) return 'At limit'
  return STATE_LABELS[account.status]
}

export function isConnected(account: CapacityAccount): boolean {
  return account.status === 'live' || account.status === 'stale' || account.status === 'rateLimited'
}

// Same wording as the dock's resetTime().
export function resetText(resetAt: number | null, now = Date.now() / 1000): string {
  if (resetAt === null) return 'No active reset'
  const seconds = Math.floor(resetAt - now)
  if (seconds <= 0) return 'Reset due'
  if (seconds >= 86400) return `Resets in ${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`
  if (seconds >= 3600) return `Resets in ${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  return `Resets in ${Math.max(1, Math.floor(seconds / 60))}m`
}

export function percentLabel(used: number | null): string {
  return used === null ? '—' : `${Math.floor(used)}%`
}

// Most constrained first; unknown capacity sorts last.
export function byConstraint(accounts: CapacityAccount[]): CapacityAccount[] {
  return [...accounts].sort((left, right) => (usedPercent(right) ?? -1) - (usedPercent(left) ?? -1))
}

export function toSnapshot(accounts: CapacityAccount[], now = Date.now() / 1000): SharedSnapshot {
  return {
    updatedAt: now,
    accounts: byConstraint(accounts).map((account) => {
      const limiting = limitingWindow(account)
      return {
        id: account.id,
        provider: account.provider,
        email: account.email.split('@')[0],
        used: usedPercent(account),
        window: limiting?.label ?? '',
        resetAt: limiting?.resetAt ?? null,
        state: stateLabel(account),
        signal: signal(account),
      }
    }),
  }
}
