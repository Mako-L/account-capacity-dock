import type { SharedAgent } from '../agents/types'
import { publishSnapshot } from './share'
import type { SharedSnapshot } from './types'

// Accounts and agents refresh apart; the widget and watch get one snapshot holding the latest of each.
let latest: SharedSnapshot = { updatedAt: 0, accounts: [], agents: [] }

export async function publishShared(patch: { accounts?: SharedSnapshot['accounts']; agents?: SharedAgent[] }) {
  latest = { ...latest, ...patch, updatedAt: Date.now() / 1000 }
  return publishSnapshot(latest).catch(() => undefined)
}
