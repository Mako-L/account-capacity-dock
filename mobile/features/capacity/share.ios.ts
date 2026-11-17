import { SharedSnapshot as Native } from '../../native/Capacity/SharedSnapshot.swift'
import type { SharedSnapshot } from './types'

export async function publishSnapshot(snapshot: SharedSnapshot): Promise<Record<string, string>> {
  return Native.publish(JSON.stringify(snapshot))
}
