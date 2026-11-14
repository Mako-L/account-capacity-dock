import { useSyncExternalStore } from 'react'
import { loadConfig } from './config'
import { fetchAccounts } from './proxy'
import { toSnapshot } from './rules'
import { publishShared } from './publish'
import type { CapacityAccount } from './types'

type State = {
  configured: boolean | null
  loading: boolean
  error: string | null
  accounts: CapacityAccount[]
  updatedAt: number | null
}

let state: State = { configured: null, loading: false, error: null, accounts: [], updatedAt: null }
const listeners = new Set<() => void>()

function update(patch: Partial<State>) {
  state = { ...state, ...patch }
  for (const listener of listeners) listener()
}

export function useCapacity(): State {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => state,
  )
}

export function accountById(id: string): CapacityAccount | undefined {
  return state.accounts.find((account) => account.id === id)
}

export async function refresh(): Promise<void> {
  if (state.loading) return
  update({ loading: true })
  try {
    const config = await loadConfig()
    if (!config) {
      update({ configured: false, loading: false, accounts: [], error: null })
      return
    }
    const accounts = await fetchAccounts(config, state.accounts)
    update({ configured: true, loading: false, accounts, error: null, updatedAt: Date.now() / 1000 })
    await publishShared({ accounts: toSnapshot(accounts).accounts })
  } catch (error) {
    update({ configured: true, loading: false, error: error instanceof Error ? error.message : 'Refresh failed.' })
  }
}
