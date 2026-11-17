import { describe, expect, test } from 'bun:test'
import {
  byConstraint,
  claudeWindows,
  codexWindows,
  limitingWindow,
  resetText,
  signal,
  stateLabel,
  toSnapshot,
  usedPercent,
} from '../rules'
import type { CapacityAccount, CapacityWindow } from '../types'

const account = (windows: CapacityWindow[], overrides: Partial<CapacityAccount> = {}): CapacityAccount => ({
  id: 'id',
  provider: 'Claude',
  email: 'person@example.com',
  plan: '',
  proxyStatus: 'active',
  status: 'live',
  message: '',
  windows,
  fetchedAt: null,
  ...overrides,
})

describe('claudeWindows', () => {
  test('reads the oauth usage body the proxy returns, in the dock order', () => {
    const windows = claudeWindows({
      five_hour: null,
      seven_day: { utilization: 100.0, resets_at: '2026-11-15T12:59:59.931556+00:00' },
      seven_day_opus: { utilization: 12.4, resets_at: null },
    })
    expect(windows).toEqual([
      { label: 'Weekly', used: 100, resetAt: Date.parse('2026-11-15T12:59:59.931556+00:00') / 1000 },
      { label: 'Weekly · Opus', used: 12.4, resetAt: null },
    ])
  })

  test('adds a weekly_scoped model limit once and skips one already named', () => {
    const windows = claudeWindows({
      seven_day: { utilization: 40, resets_at: null },
      limits: [
        { kind: 'weekly_scoped', percent: 0, resets_at: null, scope: { model: { display_name: 'Fable' } } },
        { kind: 'weekly_scoped', percent: 50, resets_at: null, scope: { model: { display_name: 'Fable' } } },
        { kind: 'session', percent: 90 },
      ],
    })
    expect(windows.map((item) => [item.label, item.used])).toEqual([
      ['Weekly', 40],
      ['Weekly · Fable', 0],
    ])
  })

  test('drops windows whose utilisation is not a finite number and clamps the rest', () => {
    const windows = claudeWindows({
      five_hour: { utilization: 'n/a' },
      seven_day: { utilization: 130 },
      seven_day_sonnet: { utilization: Number.NaN },
    })
    expect(windows).toEqual([{ label: 'Weekly', used: 100, resetAt: null }])
  })
})

describe('codexWindows', () => {
  test('labels windows by length and sorts Weekly last', () => {
    const windows = codexWindows({
      rate_limit: {
        primary_window: { used_percent: 30, limit_window_seconds: 604800, reset_at: 1795998141 },
        secondary_window: { used_percent: 64, limit_window_seconds: 18000, reset_at: 1794600000 },
      },
    })
    expect(windows.map((item) => item.label)).toEqual(['5-hour', 'Weekly'])
    expect(windows[1]).toEqual({ label: 'Weekly', used: 30, resetAt: 1795998141 })
  })

  test('calls an unknown window length Quota and removes exact duplicates', () => {
    const row = { used_percent: 45, limit_window_seconds: 2592000, reset_at: 1795998141 }
    const windows = codexWindows({ rate_limit: { primary_window: row }, secondary_rate_limit: { primary_window: row } })
    expect(windows).toEqual([{ label: 'Quota', used: 45, resetAt: 1795998141 }])
  })
})

describe('the most constrained window', () => {
  const windows = [
    { label: '5-hour', used: 20, resetAt: 100 },
    { label: 'Weekly', used: 85, resetAt: 200 },
  ]

  test('percent used and the limiting window come from the highest window', () => {
    expect(usedPercent(account(windows))).toBe(85)
    expect(limitingWindow(account(windows))?.label).toBe('Weekly')
  })

  test('an account with no windows has unknown capacity', () => {
    expect(usedPercent(account([]))).toBeNull()
    expect(limitingWindow(account([]))).toBeNull()
  })

  test('the colour thresholds match the dock', () => {
    const at = (used: number) => signal(account([{ label: 'Weekly', used, resetAt: null }]))
    expect([at(69.9), at(70), at(84.9), at(85), at(99.9), at(100)]).toEqual([
      'green',
      'yellow',
      'yellow',
      'orange',
      'orange',
      'red',
    ])
    expect(signal(account([], { status: 'loginRequired' }))).toBe('orange')
  })

  test('a live account at 100% reads At limit; other states keep their label', () => {
    expect(stateLabel(account([{ label: 'Weekly', used: 100, resetAt: null }]))).toBe('At limit')
    expect(stateLabel(account([{ label: 'Weekly', used: 100, resetAt: null }], { status: 'stale' }))).toBe('Cached')
    expect(stateLabel(account([], { status: 'rateLimited' }))).toBe('Throttled')
  })
})

describe('resetText', () => {
  const now = 1_000_000

  test('uses the dock wording at each scale', () => {
    expect(resetText(now + 2 * 86400 + 9 * 3600 + 59, now)).toBe('Resets in 2d 9h')
    expect(resetText(now + 21 * 3600 + 29 * 60, now)).toBe('Resets in 21h 29m')
    expect(resetText(now + 30, now)).toBe('Resets in 1m')
  })

  test('a past or missing reset says so', () => {
    expect(resetText(now - 1, now)).toBe('Reset due')
    expect(resetText(null, now)).toBe('No active reset')
  })
})

describe('the snapshot shared with the widget and watch', () => {
  const tight = account([{ label: 'Weekly', used: 96, resetAt: 500 }], { id: 'tight', email: 'tight@example.com' })
  const idle = account([{ label: '5-hour', used: 10, resetAt: 400 }], { id: 'idle', email: 'idle@example.com' })
  const unknown = account([], { id: 'unknown', email: 'unknown@example.com', status: 'unavailable' })

  test('sorts most constrained first and unknown capacity last', () => {
    expect(byConstraint([unknown, idle, tight]).map((item) => item.id)).toEqual(['tight', 'idle', 'unknown'])
  })

  test('carries only the display name, never the full address or anything secret', () => {
    const snapshot = toSnapshot([idle, tight, unknown], 42)
    expect(snapshot.updatedAt).toBe(42)
    expect(snapshot.accounts[0]).toEqual({
      id: 'tight',
      provider: 'Claude',
      email: 'tight',
      used: 96,
      window: 'Weekly',
      resetAt: 500,
      state: 'Available',
      signal: 'orange',
      available: true,
      tokens: null,
      costUsd: null,
    })
    expect(JSON.stringify(snapshot)).not.toContain('@')
    expect(snapshot.accounts[2]).toMatchObject({ id: 'unknown', used: null, window: '', resetAt: null })
  })
})
