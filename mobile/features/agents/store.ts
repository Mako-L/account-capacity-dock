import { One } from 'one'
import { useSyncExternalStore } from 'react'
import { loadConfig } from '../capacity/config'
import { publishShared } from '../capacity/publish'
import { defaultAgentsUrl, fetchAgents } from './client'
import { toSharedAgents } from './rules'
import type { Agent } from './types'

const URL_KEY = 'agents.url'
const IDLE_KEY = 'agents.showIdle'

type State = {
  configured: boolean | null
  loading: boolean
  error: string | null
  agents: Agent[]
  at: number | null
  showIdle: boolean
}

let state: State = {
  configured: null,
  loading: false,
  error: null,
  agents: [],
  at: null,
  showIdle: One.Storage.getItem(IDLE_KEY) === '1',
}
const listeners = new Set<() => void>()

function update(patch: Partial<State>) {
  state = { ...state, ...patch }
  for (const listener of listeners) listener()
}

export function useAgents(): State {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => state,
  )
}

export function agentById(id: string): Agent | undefined {
  return state.agents.find((agent) => agent.id === id)
}

export function savedAgentsUrl(): string {
  return One.Storage.getItem(URL_KEY) ?? ''
}

export function saveAgentsUrl(url: string): void {
  if (url) One.Storage.setItem(URL_KEY, url)
  else One.Storage.removeItem(URL_KEY)
}

export function setShowIdle(showIdle: boolean): void {
  One.Storage.setItem(IDLE_KEY, showIdle ? '1' : '0')
  update({ showIdle })
}

export async function refreshAgents(): Promise<void> {
  if (state.loading) return
  update({ loading: true })
  try {
    const config = await loadConfig()
    if (!config) {
      update({ configured: false, loading: false, agents: [], error: null })
      return
    }
    const reply = await fetchAgents(savedAgentsUrl() || defaultAgentsUrl(config.baseUrl), config)
    update({ configured: true, loading: false, agents: reply.agents, at: reply.at, error: null })
    await publishShared({ agents: toSharedAgents(reply.agents) })
  } catch (error) {
    update({ configured: true, loading: false, error: error instanceof Error ? error.message : 'Refresh failed.' })
  }
}
