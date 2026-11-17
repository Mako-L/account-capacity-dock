import type { SharedSnapshot } from './types'

// Web has no widget or watch.
export async function publishSnapshot(_snapshot: SharedSnapshot): Promise<Record<string, string>> {
  return { widget: 'unsupported', watch: 'unsupported' }
}
