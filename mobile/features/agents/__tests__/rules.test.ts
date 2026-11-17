import { describe, expect, test } from 'bun:test'
import { byAttention, currentStep, heading, progressLabel, ring, shortLabel, sinceText, stepText, toSharedAgents } from '../rules'
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
  subagents: [],
  activity: [],
  usage: null,
  totalUsage: null,
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

test('toSharedAgents keeps every agent, working first, and carries what the widget draws', () => {
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
      label: 'MASH-1',
      step: 'Testing',
      progress: 40,
      stepCount: null,
      ring: 40,
      status: 'working',
      state: 'Working',
      signal: 'yellow',
      subagents: 0,
      runningSubagents: 0,
    },
  ])
  expect(toSharedAgents(list).map((item) => item.id)).toEqual(['w', 'd', 'i'])
})

describe('shortLabel', () => {
  test('uses the ticket id when the task is one', () => {
    // Catches: the watch showing the long agent name for a ticket-flow run.
    expect(shortLabel(agent({ name: 'checkout-api', task: 'DEMO-42' }))).toBe('DEMO-42')
  })

  test('keeps the agent name when the task is a sentence', () => {
    // Catches: an unanchored ticket match picking "DEMO-42" out of free text.
    expect(shortLabel(agent({ name: 'checkout-api', task: 'Fix DEMO-42 later' }))).toBe('checkout-api')
  })

  test('ignores spaces around a ticket id', () => {
    // Catches: dropping the trim, so a padded id falls back to the name.
    expect(shortLabel(agent({ name: 'checkout-api', task: ' DEMO-42 ' }))).toBe('DEMO-42')
  })
})

test('toSharedAgents sends the counted stage pair the watch shows as 5/11', () => {
  // Catches: sending only the percentage, so the face falls back to "45%".
  const [shared] = toSharedAgents([agent({ task: 'DEMO-42', progress: 45, stepCount: [5, 11] })])

  expect(shared).toMatchObject({ label: 'DEMO-42', stepCount: [5, 11] })
})

test('toSharedAgents counts done steps when the agent has no stage pair', () => {
  // Catches: forwarding agent.stepCount alone, which is null for a plain task list.
  const steps = [{ title: 'Read', status: 'done' }, { title: 'Fix', status: 'active' }, { title: 'Test', status: 'pending' }] as Agent['steps']
  const [shared] = toSharedAgents([agent({ steps })])

  expect(shared.stepCount).toEqual([1, 3])
})

test('toSharedAgents counts subagents and the running ones', () => {
  const sub = (running: boolean) => ({
    id: running ? 'r' : 'f', name: null, description: 'Build', model: null, running, idle: !running, step: null,
    updated: null, kind: null, progress: null, phase: null, summary: null, steps: [], children: 0,
  })
  const [shared] = toSharedAgents([agent({ subagents: [sub(true), sub(false), sub(false)] })])
  expect(shared).toMatchObject({ subagents: 3, runningSubagents: 1 })
})

test('sinceText picks the largest whole unit', () => {
  expect(sinceText(null)).toBe('')
  expect(sinceText(970, 1000)).toBe('30s ago')
  expect(sinceText(1000 - 7200, 1000)).toBe('2h ago')
  expect(sinceText(1000 - 3 * 86400, 1000)).toBe('3d ago')
})
