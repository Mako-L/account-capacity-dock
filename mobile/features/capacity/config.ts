import { One } from 'one'
import type { ProxyConfig } from './types'

const URL_KEY = 'capacity.proxyUrl'
const SECRET_KEY = 'capacity.managementKey'

// The address is not secret; the management key only ever lives in the Keychain.
export async function loadConfig(): Promise<ProxyConfig | null> {
  const baseUrl = One.Storage.getItem(URL_KEY)
  if (!baseUrl) return null
  const key = await One.SecureStore.getItem(SECRET_KEY)
  return key ? { baseUrl, key } : null
}

export function savedUrl(): string {
  return One.Storage.getItem(URL_KEY) ?? ''
}

export async function hasSavedKey(): Promise<boolean> {
  return (await savedKey()) !== null
}

export function savedKey(): Promise<string | null> {
  return One.SecureStore.getItem(SECRET_KEY)
}

export async function saveConfig(baseUrl: string, key: string | null): Promise<void> {
  One.Storage.setItem(URL_KEY, baseUrl)
  if (key) await One.SecureStore.setItem(SECRET_KEY, key, { keychainAccessible: 'afterFirstUnlockThisDeviceOnly' })
}

export async function clearConfig(): Promise<void> {
  One.Storage.removeItem(URL_KEY)
  await One.SecureStore.deleteItem(SECRET_KEY)
}
