import palette from '../theme.json'
import type { AgentSignal } from '../features/agents/types'
import type { Signal } from '../features/capacity/types'

export { palette }

export function signalColor(signal: Signal | AgentSignal): string {
  return palette.signal[signal]
}
