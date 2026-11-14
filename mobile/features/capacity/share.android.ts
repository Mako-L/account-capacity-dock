import { SnapshotBridge } from '../../native/CapacityAndroid/SnapshotBridge.kt'
import type { SharedSnapshot } from './types'

export async function publishSnapshot(snapshot: SharedSnapshot): Promise<Record<string, string>> {
  return SnapshotBridge.publish(JSON.stringify(snapshot))
}
