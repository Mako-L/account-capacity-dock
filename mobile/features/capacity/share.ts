import type { SharedSnapshot } from './types'

// Web and Android have no widget or watch yet.
export async function publishSnapshot(_snapshot: SharedSnapshot): Promise<Record<string, string>> {
  return { widget: 'unsupported', watch: 'unsupported' }
}
