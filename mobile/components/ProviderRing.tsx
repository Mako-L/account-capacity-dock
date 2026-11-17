import { signal, usedPercent } from '../features/capacity/rules'
import type { CapacityAccount } from '../features/capacity/types'
import { Ring } from './Ring'

// The dock's AccountRing: quota ring with the provider mark in the middle.
export function ProviderRing({ account, size }: { account: CapacityAccount; size: number }) {
  return <Ring used={usedPercent(account)} signal={signal(account)} provider={account.provider} size={size} />
}
