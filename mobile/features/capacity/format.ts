import type { AgentUsage } from '../agents/types'
import type { WindowSpend } from './types'

// The dock's span(): 45s, 12m, 3h 20m, 2d 4h.
export function span(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  if (total < 60) return `${total}s`
  if (total < 3600) return `${Math.floor(total / 60)}m`
  if (total < 86400) {
    const minutes = Math.floor((total % 3600) / 60)
    return minutes ? `${Math.floor(total / 3600)}h ${minutes}m` : `${Math.floor(total / 3600)}h`
  }
  const hours = Math.floor((total % 86400) / 3600)
  return hours ? `${Math.floor(total / 86400)}d ${hours}h` : `${Math.floor(total / 86400)}d`
}

// The dock's formatCount(): 1.2B, 3.4M, 5.6K.
export function formatCount(value: number): string {
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`
  return String(Math.round(value))
}

export function dollars(value: number): string {
  return `$${value.toFixed(2)}`
}

// The dock's WindowSpend.line: tokens, cost and the share of a week of the plan's price.
export function spendLine(spent: WindowSpend): string {
  const plan = spent.planPercent === null ? null : `${Math.floor(spent.planPercent).toLocaleString('en-US')}% of the plan price`
  const cost = spent.costUsd === null ? null : dollars(spent.costUsd)
  return [`Used ${spent.tokens === null ? '—' : formatCount(spent.tokens)} tokens`, cost, plan].filter(Boolean).join(' · ')
}

// The agent dock's usageLine(): cost, share of a week, tokens in and out, cache.
export function usageLine(usage: AgentUsage | null): string | null {
  if (!usage) return null
  const count = (value: number | null) => {
    const amount = value ?? 0
    if (amount >= 1e9) return `${(amount / 1e9).toFixed(1)}B`
    if (amount >= 1e6) return `${(amount / 1e6).toFixed(1)}M`
    if (amount >= 1e3) return `${(amount / 1e3).toFixed(0)}K`
    return String(Math.floor(amount))
  }
  const cost = usage.cost === null ? null : dollars(usage.cost)
  const week = usage.weekPercent === null ? null : usage.weekPercent < 1 ? '<1% of a week' : `~${usage.weekPercent.toFixed(0)}% of a week`
  return [cost, week, `in ${count(usage.input)}`, `out ${count(usage.output)}`, `cache ${count(usage.cacheRead)} read · ${count(usage.cacheWrite)} write`]
    .filter(Boolean)
    .join(' · ')
}

// The agent dock's runTime(): still going, or the time from start to the last write.
export function runTime(started: number | null, updated: number | null, running: boolean, now = Date.now() / 1000): string | null {
  if (started === null) return null
  if (running) return `Running for ${span(now - started)}`
  return updated === null ? null : `Took ${span(updated - started)}`
}

// The agent dock's ago().
export function ago(timestamp: number | null, now = Date.now() / 1000): string {
  if (timestamp === null) return ''
  const seconds = Math.max(0, Math.floor(now - timestamp))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}
