import { describe, expect, test } from 'bun:test'
import { byAttention, currentStep, heading, progressLabel, ring, sinceText, stepText, toSharedAgents, visibleAgents } from '../rules'
import type { Agent } from '../types'

const agent = (overrides: Partial<Agent> = {}): Agent => ({
  id: 'a',
  agent: 'claude',
  name: 'MASH-1',
  tabName: null,
  project: null,
  status: 'working',
  title: null,
  task: null,
  now: null,
  progress: null,
  stepCount: null,
  updated: null,
  started: null,
  steps: [],
  subagents: { running: 0, total: 0 },
  ...overrides,
})

describe('heading', () => {
  test('prefers the task, then the title, then the name', () => {
    expect(heading(agent({ task: 'Fix PR', title: 'Session title' }))).toBe('Fix PR')
    expect(heading(agent({ title: 'Session title' }))).toBe('Session title')
    expect(heading(agent({ name: null }))).toBe('Claude')
  })
})

describe('ring', () => {
  test('clamps known progress to 0..100', () => {
    expect(ring(agent({ progress: 140 }))).toBe(100)
    expect(ring(agent({ progress: -5 }))).toBe(0)
  })

  test('fills a finished agent without progress and shows a short arc while working', () => {
    expect(ring(agent({ status: 'done' }))).toBe(100)
    expect(ring(agent({ status: 'working' }))).toBe(8)
    expect(ring(agent({ status: 'idle' }))).toBe(0)
  })
})

describe('steps', () => {
  const steps = [
    { title: 'Read', status: 'done' },
    { title: 'Write', status: 'active' },
    { title: 'Ship', status: 'pending' },
  ]

  test('counts finished steps when the observer gave no count', () => {
    expect(stepText(agent({ steps }))).toBe('1/3 steps')
    expect(stepText(agent({ steps, stepCount: [2, 5] }))).toBe('2/5 steps')
    expect(stepText(agent())).toBe('')
  })

  test('the current step is the observer note, else the first unfinished step', () => {
    expect(currentStep(agent({ steps, now: 'Running checks' }))).toBe('Running checks')
    expect(currentStep(agent({ steps }))).toBe('Write')
  })
})

test('progressLabel floors the percent and falls back to the state', () => {
  expect(progressLabel(agent({ progress: 97.8 }))).toBe('97%')
  expect(progressLabel(agent({ status: 'blocked' }))).toBe('Needs you')
})

test('byAttention puts blocked first, then working, finished and idle, newest first', () => {
  const order = byAttention([
    agent({ id: 'idle', status: 'idle', updated: 9 }),
    agent({ id: 'old-work', status: 'working', updated: 1 }),
    agent({ id: 'done', status: 'done', updated: 9 }),
    agent({ id: 'new-work', status: 'working', updated: 5 }),
    agent({ id: 'blocked', status: 'blocked', updated: 0 }),
  ]).map((item) => item.id)
  expect(order).toEqual(['blocked', 'new-work', 'old-work', 'done', 'idle'])
})

test('visibleAgents hides idle agents unless asked', () => {
  const list = [agent({ id: 'w' }), agent({ id: 'i', status: 'idle' })]
  expect(visibleAgents(list, false).map((item) => item.id)).toEqual(['w'])
  expect(visibleAgents(list, true)).toHaveLength(2)
})

test('toSharedAgents drops idle agents, caps the list and carries what the widget draws', () => {
  const list = [
    agent({ id: 'i', status: 'idle' }),
    agent({ id: 'w', task: 'Fix PR', progress: 40, agent: 'codex', now: 'Testing' }),
    agent({ id: 'd', status: 'done', updated: 3 }),
  ]
  const shared = toSharedAgents(list, 1)
  expect(shared).toEqual([
    {
      id: 'w',
      provider: 'Codex',
      name: 'MASH-1',
      heading: 'Fix PR',
      step: 'Testing',
      progress: 40,
      ring: 40,
      status: 'working',
      state: 'Working',
      signal: 'yellow',
    },
  ])
  expect(toSharedAgents(list).map((item) => item.id)).toEqual(['w', 'd'])
})

test('sinceText picks the largest whole unit', () => {
  expect(sinceText(null)).toBe('')
  expect(sinceText(970, 1000)).toBe('30s ago')
  expect(sinceText(1000 - 7200, 1000)).toBe('2h ago')
  expect(sinceText(1000 - 3 * 86400, 1000)).toBe('3d ago')
})
