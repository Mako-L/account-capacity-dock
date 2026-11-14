import palette from '../theme.json'
import type { Signal } from '../features/capacity/types'

export { palette }

export function signalColor(signal: Signal): string {
  return palette.signal[signal]
}
